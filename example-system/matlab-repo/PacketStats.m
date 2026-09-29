classdef PacketStats
    %PACKETSTATS Frame counters for one recording (value class, single-file classdef).
    properties
        Frames (1,1) double = 0
        Bad (1,1) double = 0
        Seen containers.Map
    end
    methods
        function obj = PacketStats(frames)
            obj.Frames = numel(frames.seq);
            obj.Seen = containers.Map('KeyType', 'double', 'ValueType', 'double');
        end
        function obj = update(obj, bad)
            obj.Bad = obj.Bad + numel(bad);
            for b = bad(:)'
                if isKey(obj.Seen, b)
                    obj.Seen(b) = obj.Seen(b) + 1;
                else
                    obj.Seen(b) = 1;
                end
            end
        end
        function r = dropRate(obj)
            if obj.Frames == 0
                r = 0;
            else
                r = obj.Bad / obj.Frames;
            end
        end
    end
end
