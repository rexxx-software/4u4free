/*
 * 4u4free.PlaytimeIdler
 * Copyright (c) 2026 4u4free contributors
 *
 * This file is part of 4u4free and is licensed under GPL-3.0-or-later.
 * It dynamically uses the unmodified SAM.API library by Rick (gibbed), which
 * is distributed separately under the zlib license. This helper only holds a
 * SteamAPI presence for an app the signed-in account is subscribed to. It does
 * not read credentials or write achievements, stats, configuration, or saves.
 */

using System;
using System.Diagnostics;
using System.Threading;

namespace FourUFourFree.PlaytimeIdler
{
    internal static class Program
    {
        private static readonly ManualResetEventSlim StopRequested = new(false);

        public static int Main(string[] args)
        {
            if (args.Length != 2 ||
                uint.TryParse(args[0], out uint appId) == false ||
                appId == 0 ||
                int.TryParse(args[1], out int parentProcessId) == false ||
                parentProcessId <= 0)
            {
                Console.Error.WriteLine("Usage: 4u4free.PlaytimeIdler.exe <AppID> <parent PID>");
                return 2;
            }

            Process parent;
            try
            {
                parent = Process.GetProcessById(parentProcessId);
            }
            catch (ArgumentException)
            {
                Console.Error.WriteLine("The 4u4free parent process is not running.");
                return 3;
            }

            Thread inputThread = new(() =>
            {
                try
                {
                    Console.ReadLine();
                }
                catch (Exception)
                {
                    // A closed pipe is also a request to stop.
                }
                StopRequested.Set();
            })
            {
                IsBackground = true,
                Name = "4u4free idler stop listener",
            };
            inputThread.Start();

            try
            {
                using SAM.API.Client client = new();
                client.Initialize(appId);
                if (client.SteamApps008 == null ||
                    client.SteamApps008.IsSubscribedApp(appId) == false)
                {
                    Console.Error.WriteLine(
                        $"The signed-in Steam account has no valid license for App {appId}.");
                    return 5;
                }

                Console.WriteLine($"READY {appId}");
                Console.Out.Flush();

                while (StopRequested.Wait(500) == false)
                {
                    if (parent.HasExited)
                    {
                        break;
                    }
                    client.RunCallbacks(false);
                }
            }
            catch (SAM.API.ClientInitializeException exception)
            {
                Console.Error.WriteLine($"SteamAPI initialization failed: {exception.Message}");
                return 4;
            }
            catch (DllNotFoundException exception)
            {
                Console.Error.WriteLine($"Steam client library could not be loaded: {exception.Message}");
                return 6;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine($"Playtime idler failed: {exception.Message}");
                return 7;
            }
            finally
            {
                parent.Dispose();
            }

            return 0;
        }
    }
}
