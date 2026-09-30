function y = moving_avg_rt(x, n)
%MOVING_AVG_RT Sliding mean of the last N samples with warm-up, truncated toward zero.
%   Same contract as ../model/moving_avg.m (SN-REQ-003); this copy works on double input and
%   returns double so the soak scripts can filter calibrated temperatures.
if nargin < 2
    n = 4;
end
x = x(:);
y = zeros(numel(x), 1);
for k = 1:numel(x)
    lo = max(1, k - n + 1);
    w = x(lo:k);
    y(k) = fix(sum(w) / numel(w));
end
end
