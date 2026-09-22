%EXPORT_VECTORS Write the golden vectors for moving_avg to filter_vectors.csv.
%   Run once in MATLAB from this folder after changing moving_avg.m. The CSV is what the firmware
%   twins are checked against (../tests/test_model_equivalence.py), so a model change that alters
%   any row is visible in the diff of this file before it is visible in a failing firmware test.
%
%   The sample list deliberately covers warm-up, negative sums that do not divide evenly,
%   both int16 extremes in a row, and a sign change inside the window.

samples = int16([100 200 300 400 800 -1 -1 -1 -1 0 ...
                 32767 32767 32767 32767 -32768 -32768 -32768 -32768 ...
                 -5 2 -4 1 7 7 7 7])';

filtered = moving_avg(samples, 4);
k = (1:numel(samples))';

T = table(k, samples, filtered, 'VariableNames', {'k', 'sample', 'filtered'});
writetable(T, 'filter_vectors.csv');
fprintf('wrote %d rows to filter_vectors.csv\n', height(T));
