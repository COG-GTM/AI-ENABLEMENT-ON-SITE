function [ok, viol] = check_limits(values, lim, handler)
%CHECK_LIMITS Flag samples outside [lim.low, lim.high] with hysteresis; call handler per violation.
%   handler is a function handle (or a function name as a string, for legacy callers). The string
%   form goes through feval, which static analysis cannot resolve; see the repo map.
viol = [];
inside = true;
for k = 1:numel(values)
    v = values(k);
    if inside && (v > lim.high || v < lim.low)
        inside = false;
        viol(end + 1) = k; %#ok<AGROW>
        if nargin >= 3
            feval(handler, k, v);
        end
    elseif ~inside && v < lim.high - lim.hysteresis && v > lim.low + lim.hysteresis
        inside = true;
    end
end
ok = isempty(viol);
end
