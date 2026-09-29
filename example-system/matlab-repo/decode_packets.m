function [frames, bad] = decode_packets(raw)
%DECODE_PACKETS Split a byte stream into 6-byte frames and verify each CRC-8.
%   raw    uint8 vector
%   frames struct with fields adc (uint16 column) and seq (uint8 column)
%   bad    indices of frames whose CRC did not match
%
%   Mirrors ../src/packet.c: frame = [0xA5 seq adc_hi adc_lo status crc]; CRC-8 poly 0x07 over bytes 1..5.
n = floor(numel(raw) / 6);
adc = zeros(n, 1, 'uint16');
seq = zeros(n, 1, 'uint8');
bad = [];
for i = 1:n
    f = raw((i - 1) * 6 + (1:6));
    if f(1) ~= hex2dec('A5') || crc8(f(1:5)) ~= f(6)
        bad(end + 1) = i; %#ok<AGROW>
        continue
    end
    seq(i) = f(2);
    adc(i) = bitor(bitshift(uint16(f(3)), 8), uint16(f(4)));
end
frames.adc = adc;
frames.seq = seq;
end

function c = crc8(bytes)
%CRC8 Local function: polynomial 0x07, init 0, no reflection (same table as src/crc8.c).
c = uint8(0);
for b = bytes(:)'
    c = bitxor(c, b);
    for k = 1:8
        if bitand(c, uint8(128))
            c = bitxor(bitshift(c, 1), uint8(7));
        else
            c = bitshift(c, 1);
        end
    end
end
end
