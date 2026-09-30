% PLOT_SOAK Script: graphics only, no algorithm. Kept in MATLAB; the Python twin has no equivalent.
figure('Name', 'Soak');
subplot(2, 1, 1);
plot(temp_f);
ylabel('deg C');
subplot(2, 1, 2);
stem(viol, ones(size(viol)));
xlabel('sample');
title(sprintf('%d violations', numel(viol)));
