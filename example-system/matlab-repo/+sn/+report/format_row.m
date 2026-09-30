function s = format_row(k, value, flag)
%FORMAT_ROW One fixed-width report line.
if flag
    tag = 'LIMIT';
else
    tag = 'ok';
end
s = sprintf('%6d %9.3f %s', k, value, tag);
end
