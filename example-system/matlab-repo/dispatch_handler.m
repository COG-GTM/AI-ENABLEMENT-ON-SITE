function out = dispatch_handler(name, varargin)
%DISPATCH_HANDLER Route a request to a handler chosen at run time.
%   Three dynamic forms static analysis cannot resolve: eval of a built string, str2func, and run of
%   a script name. They are here so the repo map shows how such calls are reported.
switch name
    case 'hex'
        f = str2func('hexstr');
        out = f(varargin{1});
    case 'report'
        out = eval(['sn.report.format_row(' num2str(varargin{1}) ', 0, false)']);
    case 'setup'
        run('setup_paths');
        out = [];
    otherwise
        error('soak:dispatch', 'unknown handler %s', name);
end
end
