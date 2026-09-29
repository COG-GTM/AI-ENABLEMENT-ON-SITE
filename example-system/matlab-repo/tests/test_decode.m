% TEST_DECODE Script-based test: known frames decode, corrupted CRC is reported.
frame = uint8([hex2dec('A5') 1 1 44 0 0]);
frame(6) = crc8_ref(frame(1:5));
[frames, bad] = decode_packets([frame frame]);
assert(isempty(bad));
assert(all(frames.adc == 300));
frame(6) = bitxor(frame(6), 1);
[~, bad] = decode_packets(frame);
assert(isequal(bad, 1));

function c = crc8_ref(bytes)
c = uint8(0);
for b = bytes(:)'
    c = bitxor(c, b);
    for k = 1:8
        if bitand(c, uint8(128)), c = bitxor(bitshift(c, 1), uint8(7)); else, c = bitshift(c, 1); end
    end
end
end
