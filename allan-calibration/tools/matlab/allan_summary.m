function s = allan_summary(tau, adev)
%ALLAN_SUMMARY  Noise figures read from an Allan deviation curve of a gyro axis [deg/s].
%   ARW [deg/sqrt(h)]       curve value at tau = 1 s times 60; valid only if the curve follows the -1/2 slope there
%                           (slope_at_1s is returned for that check).
%   bias instability [deg/h] curve minimum / 0.664; valid only if the curve has stopped falling
%                           (bias_instability_observed: log-log slope over the last decade of tau above -0.25).
% Same rules as tools/imu_daq/analysis.py.
s = struct('arw_deg_per_sqrt_h', NaN, 'slope_at_1s', NaN, 'bias_instability_deg_per_h', NaN, ...
           'bias_instability_tau_s', NaN, 'bias_instability_observed', false, 'slope_last_decade', NaN, 'tau_max_s', NaN);
if numel(tau) < 3, return; end
tau = tau(:); adev = adev(:);
lt = log10(tau); la = log10(adev);
s.tau_max_s = tau(end);
if tau(1) <= 1 && 1 <= tau(end)
    s.arw_deg_per_sqrt_h = 10 ^ interp1(lt, la, 0) * 60;
    sel = tau >= 0.4 & tau <= 2.5;
    if sum(sel) >= 2
        p = polyfit(lt(sel), la(sel), 1); s.slope_at_1s = p(1);
    end
end
[amin, k] = min(adev);
s.bias_instability_deg_per_h = amin / 0.664 * 3600;
s.bias_instability_tau_s = tau(k);
tail = tau >= tau(end) / 10;
if sum(tail) >= 3
    p = polyfit(lt(tail), la(tail), 1); s.slope_last_decade = p(1);
    s.bias_instability_observed = p(1) > -0.25;
end
end
