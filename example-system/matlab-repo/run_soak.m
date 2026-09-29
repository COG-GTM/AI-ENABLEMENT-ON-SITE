% RUN_SOAK Top-level entry point: replay a recorded soak test through the sensor-node algorithms.
%   Loads a recording, decodes the packets, calibrates temperature, filters, checks limits, and
%   writes a report. This is a script (no function line): the workspace is the state.
%
%   Usage:  run_soak            (from the repository root, after setup_paths)

setup_paths;
cfg = sn.config.defaults();                 % package function, resolved through +sn/+config
rec = load_recording('recordings/soak_2h.csv');
[frames, bad] = decode_packets(rec.raw);
temp_c = calibrate_temperature(frames.adc, cfg.cal);
temp_f = moving_avg_rt(temp_c, cfg.window);
[ok, viol] = check_limits(temp_f, cfg.limits, @on_violation);
stats = PacketStats(frames);
stats = stats.update(bad);
write_report('outputs/soak-report.txt', temp_f, viol, stats);
if ~ok
    warning('soak:limits', '%d limit violations', numel(viol));
end

function on_violation(idx, value)
    fprintf('violation at %d: %.2f\n', idx, value);
end
