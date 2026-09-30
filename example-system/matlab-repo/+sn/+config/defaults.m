function cfg = defaults()
%DEFAULTS Configuration record shared by the soak scripts.
cfg.window = 4;
cfg.cal = struct('gain', 0.0625, 'offset', -40, 'poly', [0.0625 -40]);
cfg.limits = sn.limits.default_limits();
cfg.version = sn.version();
end
