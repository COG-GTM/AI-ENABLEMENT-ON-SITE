function write_report(path, values, viol, stats)
%WRITE_REPORT Plain-text soak report: one row per sample plus a packet summary.
flags = false(size(values));
flags(viol) = true;
fid = fopen(path, 'w');
if fid < 0
    error('soak:report', 'cannot open %s', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '# soak report, algorithm set %s\n', sn.version());
for k = 1:numel(values)
    fprintf(fid, '%s\n', sn.report.format_row(k, values(k), flags(k)));
end
fprintf(fid, '# frames %d, bad %d, drop rate %.4f\n', stats.Frames, stats.Bad, stats.dropRate());
end
