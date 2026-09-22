function y = moving_avg(x, n)
%MOVING_AVG Sliding mean of the last N samples, integer result, truncated toward zero.
%   y = MOVING_AVG(x, n) takes a vector x of int16-range samples and returns an int16 column
%   vector y where y(k) is the mean of x(max(1, k-n+1) : k). n defaults to 4.
%
%   Reference model for SN-REQ-003 (4-sample moving average). The firmware in ../src/filter.c and
%   the Python twin in ../sim/sensor_node/filter.py must match this row for row. The golden vectors
%   in filter_vectors.csv were produced by export_vectors.m from this function, and
%   ../tests/test_model_equivalence.py replays them through both twins.
%
%   Two rules decide whether a port matches (see MODEL-NOTES.md):
%     1. Warm-up: the first n-1 outputs average only the samples seen so far (count = k), not n.
%     2. Rounding: the mean is truncated toward zero (fix), which is what C integer division does.
%        MATLAB integer arithmetic rounds to nearest (int16(-3) / int16(4) is -1, not 0), so a
%        model written as int16(sum(w)) / int16(numel(w)) disagrees with the firmware on negative
%        sums that do not divide evenly. Row 8 of filter_vectors.csv is that case.

    if nargin < 2
        n = 4;
    end
    validateattributes(x, {'numeric'}, {'vector', 'integer', '>=', -32768, '<=', 32767});
    validateattributes(n, {'numeric'}, {'scalar', 'integer', '>=', 1});

    x = double(x(:));                 % accumulate in double: n * 32767 would overflow int16
    y = zeros(numel(x), 1, 'int16');
    for k = 1:numel(x)
        lo = max(1, k - n + 1);       % 1-based, inclusive; the C ring buffer is 0-based
        w = x(lo:k);
        y(k) = int16(fix(sum(w) / numel(w)));
    end
end
