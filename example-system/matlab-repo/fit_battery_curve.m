function p = fit_battery_curve(soc, voltage)
%FIT_BATTERY_CURVE Fit voltage = f(soc) for the discharge curve.
%   lsqcurvefit needs the Optimization Toolbox; the fallback uses polyfit (core).
model = @(p, x) p(1) + p(2) * x + p(3) * exp(-p(4) * x);
if license('test', 'Optimization_Toolbox')
    p = lsqcurvefit(model, [3.2 0.01 0.5 0.1], soc(:), voltage(:));
else
    q = polyfit(soc(:), voltage(:), 2);
    p = [q(3) q(2) 0 0];
end
end
