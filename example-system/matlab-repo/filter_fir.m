function y = filter_fir(x, cutoff, fs)
%FILTER_FIR Low-pass an oversampled channel before decimation.
%   fir1 and freqz are Signal Processing Toolbox; filter and fft are core MATLAB.
b = fir1(32, cutoff / (fs / 2));
y = filter(b, 1, x);
if nargout == 0
    freqz(b, 1, 512, fs);
end
end
