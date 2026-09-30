function tests = test_limits
%TEST_LIMITS Function-based unit tests for check_limits (run with: runtests('tests')).
tests = functiontests(localfunctions);
end

function testInsideStaysOk(t)
lim = sn.limits.default_limits();
[ok, viol] = check_limits([20 21 22], lim);
verifyTrue(t, ok);
verifyEmpty(t, viol);
end

function testSpikeIsOneViolation(t)
lim = sn.limits.default_limits();
[ok, viol] = check_limits([20 90 91 20], lim);
verifyFalse(t, ok);
verifyEqual(t, viol, 2);
end
