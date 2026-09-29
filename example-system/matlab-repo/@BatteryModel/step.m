function soc = step(obj, current_ma, dt_s)
%STEP Integrate current over dt and clamp state of charge to [0, 100].
used_mah = current_ma * dt_s / 3600;
obj.SocPct = min(100, max(0, obj.SocPct - 100 * used_mah / obj.CapacityMah));
soc = obj.SocPct;
end
