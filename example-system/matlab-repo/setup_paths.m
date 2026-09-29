% SETUP_PATHS Add the repository folders to the MATLAB path. Path order decides which of two
% same-named functions wins (see legacy/max.m), so this script is the source of truth for it.
here = fileparts(mfilename('fullpath'));
addpath(here);
addpath(fullfile(here, 'util'));
addpath(fullfile(here, 'legacy'));   % legacy last: its max.m shadows the built-in when first
