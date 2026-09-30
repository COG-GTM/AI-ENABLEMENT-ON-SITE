function m = max(varargin)
%MAX Shadows the MATLAB built-in max when legacy/ is first on the path. Returns the same result for
%   the two-argument form and errors otherwise, which is how a soak run once failed in the field.
if nargin == 2
    m = builtin('max', varargin{:});
else
    error('legacy:max', 'legacy max supports two arguments only');
end
end
