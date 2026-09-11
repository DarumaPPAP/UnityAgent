using System;
using System.Diagnostics;
using System.Text;

namespace DarumaPPAP.UnityAgent.Editor
{
    internal static class UnityAgentControlPlaneClient
    {
        internal static bool TryRun(
            string operation,
            string projectPath,
            string hostCommand,
            string expectedPlanId,
            string approvalRef,
            out string output,
            out string error)
        {
            output = string.Empty;
            error = string.Empty;
            if (operation != "doctor" && operation != "plan" && operation != "apply")
            {
                error = "UnityAgent Control Plane operation must be doctor, plan or apply.";
                return false;
            }

            var arguments = new StringBuilder();
            arguments.Append("setup --operation ").Append(Quote(operation));
            arguments.Append(" --project-path ").Append(Quote(projectPath));
            arguments.Append(" --format json --non-interactive");
            if (!string.IsNullOrEmpty(expectedPlanId))
            {
                arguments.Append(" --expected-plan-id ").Append(Quote(expectedPlanId));
            }
            if (!string.IsNullOrEmpty(approvalRef))
            {
                arguments.Append(" --approval-ref ").Append(Quote(approvalRef));
            }

            try
            {
                using (var process = new Process())
                {
                    process.StartInfo = new ProcessStartInfo
                    {
                        FileName = string.IsNullOrEmpty(hostCommand) ? "unity-agent" : hostCommand,
                        Arguments = arguments.ToString(),
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                    };
                    if (!process.Start())
                    {
                        error = "UnityAgent Control Plane process could not start.";
                        return false;
                    }

                    output = process.StandardOutput.ReadToEnd();
                    error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    if (process.ExitCode != 0)
                    {
                        if (string.IsNullOrEmpty(error))
                        {
                            error = "UnityAgent Control Plane returned exit code " + process.ExitCode + ".";
                        }
                        return false;
                    }
                    return true;
                }
            }
            catch (Exception exception)
            {
                error = exception.Message;
                return false;
            }
        }

        private static string Quote(string value)
        {
            return "\"" + (value ?? string.Empty).Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
        }
    }
}
