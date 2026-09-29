function temp_c = calibrate_temperature(adc, cal)
%CALIBRATE_TEMPERATURE ADC counts to degrees C with a first-order polynomial (SN-REQ-002).
%   polyval is core MATLAB; interp1 is used for the optional lookup-table path.
adc = double(adc(:));
if isfield(cal, 'lut')
    temp_c = interp1(cal.lut.counts, cal.lut.deg_c, adc, 'linear', 'extrap');
else
    temp_c = polyval(cal.poly, adc);
end
temp_c = round(temp_c * 100) / 100;
end
