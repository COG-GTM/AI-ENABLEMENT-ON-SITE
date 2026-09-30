function rec = load_recording(path)
%LOAD_RECORDING Read a CSV recording (columns t_ms, raw) into a struct of column vectors.
%   Uses readtable, which is core MATLAB; the Python twin uses the csv module.
if ~isfile(path)
    error('soak:missingRecording', 'recording not found: %s', path);
end
if endsWith(path, '.tdms')
    t = tdms_read(path);            % third-party reader from a file exchange; not in this tree
else
    t = readtable(path);
end
rec.t_ms = t.t_ms;
rec.raw = uint8(t.raw);
rec.source = path;
end
