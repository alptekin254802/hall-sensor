"""Small 1-D calibrators; training-only transforms, explicit support, JSON persistence."""
import numpy as np
from .io import finite, seal, verify, read_json, write_json


class Calibrator:
    def __init__(self, state):
        self.state = state

    @classmethod
    def fit(cls, x, y, spec, weights=None):
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        if x.ndim != 1 or y.shape != x.shape or len(x) < 2:
            raise ValueError("Calibration requires at least two 1-D paired observations")
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise ValueError("Nonfinite calibration data")
        w = np.ones(len(x)) if weights is None else np.asarray(weights, dtype=float)
        if w.shape != x.shape or not np.all(np.isfinite(w)) or np.any(w <= 0):
            raise ValueError("Positive finite training weights required")
        w = w / w.sum()
        if np.ptp(x) == 0 or np.ptp(y) == 0:
            raise ValueError("Calibration must span input and reference force")
        kind = spec["kind"]
        allowed = {"kind", "out_of_range", "monotonic"}
        allowed |= {"degree"} if kind == "polynomial" else set()
        allowed |= {"hidden", "epochs", "learning_rate", "seed"} if kind == "mlp" else set()
        if set(spec) - allowed: raise ValueError("Unknown model setting")
        policy = spec["out_of_range"]
        monotonic = spec["monotonic"]
        if policy not in {"reject", "extrapolate"}: raise ValueError("No implicit clipping policy")
        if monotonic not in {"none", "increasing", "decreasing"}: raise ValueError("Unknown monotonic requirement")
        mu = float(np.dot(w, x)); scale = float(np.sqrt(np.dot(w, (x-mu)**2)))
        z = (x-mu)/scale
        unique, counts = np.unique(x, return_counts=True)
        conflicts = [{"input": float(v), "count": int(n),
                      "reference_min_N": float(y[x == v].min()), "reference_max_N": float(y[x == v].max())}
                     for v, n in zip(unique, counts) if n > 1]
        state = dict(spec=spec, bounds=[float(x.min()), float(x.max())],
                     reference_bounds_N=[float(y.min()), float(y.max())],
                     x_mean=mu, x_scale=scale, numpy_version=np.__version__,
                     training_rows=len(x), duplicate_inputs=conflicts,
                     continuity="Continuous mathematical mapping on fitted support; not hardware validation")
        order = np.argsort(x, kind="stable")
        dx, dy = np.diff(x[order]), np.diff(y[order])
        state["raw_anchor_diagnostics"] = {
            "negative_force_steps_with_increasing_input": int(np.sum((dx > 0) & (dy < 0))),
            "positive_force_steps_with_increasing_input": int(np.sum((dx > 0) & (dy > 0))),
            "note": "Raw observed pairs are not corrected; step signs describe sorted inputs, not temporal hysteresis"}
        if kind in {"linear", "polynomial"}:
            degree = 1 if kind == "linear" else spec["degree"]
            if type(degree) is not int or not 1 <= degree <= 3:
                raise ValueError("Explicit polynomial degree 1..3 required")
            design = np.polynomial.polynomial.polyvander(z, degree)
            coeff, _, rank, singular = np.linalg.lstsq(design*np.sqrt(w[:, None]), y*np.sqrt(w), rcond=None)
            if rank != degree + 1: raise ValueError("Rank-deficient calibration support")
            state.update(coefficients=coeff.tolist(), degree=degree,
                         condition_number=float(singular[0]/singular[-1]))
            derivative = np.polynomial.polynomial.polyder(coeff)
            second = np.polynomial.polynomial.polyder(derivative)
            critical = np.polynomial.polynomial.polyroots(second) if len(second) > 1 else []
            support = [float(z.min()), float(z.max())]
            support += [float(r.real) for r in critical if abs(r.imag) < 1e-12 and z.min() < r.real < z.max()]
            slopes = np.polynomial.polynomial.polyval(support, derivative)/scale
            state["derivative_range"] = [float(min(slopes)), float(max(slopes))]
            state["monotonic_check"] = "Polynomial derivative extrema on fitted interval"
            if monotonic == "increasing" and min(slopes) < -1e-12:
                raise ValueError("Fitted polynomial reverses on its support")
            if monotonic == "decreasing" and max(slopes) > 1e-12:
                raise ValueError("Fitted polynomial reverses on its support")
        elif kind == "interpolation":
            if monotonic == "none": raise ValueError("Interpolation needs an explicit monotonic direction")
            if conflicts: raise ValueError("Duplicate interpolation inputs; inspect raw anchors, no automatic merging")
            order = np.argsort(x); xp, yp = x[order], y[order]
            delta = np.diff(yp)
            if (monotonic == "increasing" and np.any(delta < 0)) or (monotonic == "decreasing" and np.any(delta > 0)):
                raise ValueError("Nonmonotonic interpolation anchors; no automatic monotonization")
            state.update(x_knots=xp.tolist(), y_knots_N=yp.tolist(),
                         monotonic_check="All adjacent anchor slopes; repeated force values permitted")
        elif kind == "mlp":
            if monotonic != "none": raise ValueError("This MLP does not guarantee monotonicity")
            hidden, epochs, seed = spec["hidden"], spec["epochs"], spec["seed"]
            lr = finite(spec["learning_rate"], "learning rate")
            if type(hidden) is not int or not 1 <= hidden <= 16 or type(epochs) is not int or not 1 <= epochs <= 5000:
                raise ValueError("Small fixed MLP required (1..16 hidden units, 1..5000 epochs)")
            if type(seed) is not int or not 0 <= seed < 2**32 or not 0 < lr <= .1:
                raise ValueError("Invalid seed or learning rate")
            ym = float(np.dot(w, y)); ys = float(np.sqrt(np.dot(w, (y-ym)**2)))
            target = (y-ym)/ys
            rng = np.random.default_rng(seed)
            params = [rng.normal(0, .3, hidden), np.zeros(hidden), rng.normal(0, .3, hidden), np.zeros(1)]
            first = [np.zeros_like(v) for v in params]; second = [np.zeros_like(v) for v in params]
            # Fixed full-batch Adam. No early stopping or implicit validation split.
            for epoch in range(1, epochs+1):
                a = np.tanh(z[:, None]*params[0]+params[1])
                prediction = a @ params[2]+params[3][0]
                d = 2*w*(prediction-target)
                hidden_d = d[:, None]*params[2]*(1-a*a)
                grads = [(hidden_d*z[:, None]).sum(axis=0), hidden_d.sum(axis=0),
                         a.T @ d, np.array([d.sum()])]
                for i, grad in enumerate(grads):
                    first[i] = .9*first[i]+.1*grad
                    second[i] = .999*second[i]+.001*grad*grad
                    params[i] -= lr*(first[i]/(1-.9**epoch))/(np.sqrt(second[i]/(1-.999**epoch))+1e-8)
            if not all(np.all(np.isfinite(v)) for v in params): raise ValueError("MLP training diverged")
            state.update(parameters=[v.tolist() for v in params], y_mean=ym, y_scale=ys,
                         training="Fixed epochs, full-batch weighted MSE, Adam; no validation/early stopping/augmentation",
                         inference_environment="Python host; not STM32 execution")
        else:
            raise ValueError("Unknown calibration family")
        return cls(state)

    def _values(self, x):
        s = self.state; kind = s["spec"]["kind"]
        z = (x-s["x_mean"])/s["x_scale"]
        if kind in {"linear", "polynomial"}:
            return np.polynomial.polynomial.polyval(z, s["coefficients"])
        if kind == "mlp":
            w, b, v, c = map(np.asarray, s["parameters"])
            return (np.tanh(z[:, None]*w+b) @ v+c[0])*s["y_scale"]+s["y_mean"]
        xp, yp = np.asarray(s["x_knots"]), np.asarray(s["y_knots_N"])
        out = np.interp(x, xp, yp)
        # np.interp's default endpoint clamp is deliberately replaced by explicit extrapolation.
        left, right = x < xp[0], x > xp[-1]
        out[left] = yp[0]+(x[left]-xp[0])*(yp[1]-yp[0])/(xp[1]-xp[0])
        out[right] = yp[-1]+(x[right]-xp[-1])*(yp[-1]-yp[-2])/(xp[-1]-xp[-2])
        return out

    def predict(self, x):
        values = np.asarray(x, dtype=float)
        if values.ndim != 1 or not np.all(np.isfinite(values)): raise ValueError("Finite 1-D inputs required")
        out = self._values(values)
        lo, hi = self.state["bounds"]
        result = []
        for value, prediction in zip(values, out):
            outside = not lo <= value <= hi
            status = "out_of_range_extrapolated" if outside else "ok"
            if outside and self.state["spec"]["out_of_range"] == "reject":
                result.append({"value_N": None, "status": "out_of_range_rejected"})
            elif not np.isfinite(prediction):
                result.append({"value_N": None, "status": "nonfinite_model_output"})
            else:
                result.append({"value_N": float(prediction), "status": status})
        return result

    def save(self, path):
        write_json(path, seal(dict(state=self.state), "model_id"))

    @classmethod
    def load(cls, path):
        return cls(verify(read_json(path), "model_id")["state"])
