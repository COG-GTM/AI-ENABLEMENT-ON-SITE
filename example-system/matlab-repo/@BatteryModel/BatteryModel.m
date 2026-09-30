classdef BatteryModel < handle
    %BATTERYMODEL Coulomb-counting state of charge (SN-REQ-006). @folder class: methods in sibling files.
    properties
        CapacityMah double
        SocPct double = 100
    end
    methods
        function obj = BatteryModel(capacity_mah)
            obj.CapacityMah = capacity_mah;
        end
        soc = step(obj, current_ma, dt_s)
    end
end
