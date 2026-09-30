function y = clamp(x, lo, hi)
%CLAMP Private helper: visible only to functions in the parent folder.
y = min(hi, max(lo, x));
end
