function s = hexstr(bytes)
%HEXSTR Upper-case hex string of a byte vector, no separators. Called through str2func in dispatch_handler.
s = upper(reshape(dec2hex(bytes(:), 2)', 1, []));
end
