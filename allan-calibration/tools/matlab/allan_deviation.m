function [tau, adev] = allan_deviation(x, rate_hz, n_taus)
%ALLAN_DEVIATION  Overlapping Allan deviation of a rate signal x [deg/s] sampled at rate_hz.
%   [tau, adev] = allan_deviation(gyro(:,1), 1000)
% Same algorithm as tools/imu_daq/analysis.py (cumulative-sum form, O(N) per tau).
if nargin < 3, n_taus = 25; end
x = x(:);
n = numel(x);
theta = [0; cumsum(x)] / rate_hz;            % integrated angle
m_max = floor(n / 3);
if m_max < 1, tau = []; adev = []; return; end
ms = unique(floor(logspace(0, log10(m_max), n_taus)));
tau = zeros(numel(ms), 1); adev = zeros(numel(ms), 1);
for k = 1:numel(ms)
    m = ms(k);
    d = theta(2*m+1:end) - 2*theta(m+1:end-m) + theta(1:end-2*m);
    tau(k)  = m / rate_hz;
    adev(k) = sqrt(0.5 * mean(d.^2)) / (m / rate_hz);
end
end
