function frames = old_decode(raw)
%OLD_DECODE Pre-CRC decoder kept for comparison. Nothing calls it: a candidate for deletion, not migration.
n = floor(numel(raw) / 4);
frames = zeros(n, 1, 'uint16');
for i = 1:n
    frames(i) = double(raw((i - 1) * 4 + 2)) * 256 + double(raw((i - 1) * 4 + 3));
end
end
