using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Program
{
    private const string Magic = "LVAIPAYLOADV1.0!";
    private const string AppName = "LocalVideoAI";
    private const string AppDisplay = "LocalVideoAI Translator";
    private const string AppExe = "LocalVideoAI.exe";
    private const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalVideoAI";

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            Options options = Options.Parse(args);
            if (options.Uninstall)
            {
                return Uninstaller.Run(options);
            }
            if (options.Silent)
            {
                Installer.RunSilent(options);
                return 0;
            }
            Application.Run(new WizardForm(options));
            return 0;
        }
        catch (Exception ex)
        {
            if (IsSilent(args))
            {
                Console.Error.WriteLine(ex.Message);
            }
            else
            {
                MessageBox.Show(ex.Message, AppDisplay, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            return 1;
        }
    }

    private static bool IsSilent(string[] args)
    {
        foreach (string arg in args)
        {
            string upper = arg.ToUpperInvariant();
            if (upper == "/SILENT" || upper == "/VERYSILENT" || upper == "/S")
            {
                return true;
            }
        }
        return false;
    }

    internal static string DefaultInstallDir()
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        return Path.Combine(local, "Programs", AppName);
    }

    internal static string DefaultDataDir(string name)
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        return Path.Combine(local, AppName, name);
    }

    internal static string DefaultPortableDir()
    {
        return Path.Combine(Environment.CurrentDirectory, AppName);
    }
}

internal sealed class Options
{
    public bool Silent;
    public bool Portable;
    public bool Uninstall;
    public bool DesktopIcon = true;
    public bool LaunchAfter = true;
    public string InstallDir = Program.DefaultInstallDir();
    public string ModelsDir = Program.DefaultDataDir("models");
    public string ProjectsDir = Program.DefaultDataDir("projects");
    public string CacheDir = Program.DefaultDataDir("cache");
    public string UninstallMode = "program";

    public static Options Parse(string[] args)
    {
        Options options = new Options();
        string exe = Application.ExecutablePath ?? "";
        string name = Path.GetFileNameWithoutExtension(exe) ?? "";
        if (name.IndexOf("Portable", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            options.Portable = true;
            options.InstallDir = Program.DefaultPortableDir();
            options.LaunchAfter = true;
        }
        if (name.Equals("Uninstall", StringComparison.OrdinalIgnoreCase)
            || name.Equals("UninstallLocalVideoAI", StringComparison.OrdinalIgnoreCase))
        {
            options.Uninstall = true;
        }

        foreach (string raw in args)
        {
            if (string.IsNullOrWhiteSpace(raw))
            {
                continue;
            }
            string arg = raw.Trim();
            string upper = arg.ToUpperInvariant();
            if (upper == "/SILENT" || upper == "/VERYSILENT" || upper == "/S")
            {
                options.Silent = true;
                options.LaunchAfter = false;
            }
            else if (upper == "/PORTABLE")
            {
                options.Portable = true;
                if (string.IsNullOrEmpty(options.InstallDir) || options.InstallDir == Program.DefaultInstallDir())
                {
                    options.InstallDir = Program.DefaultPortableDir();
                }
            }
            else if (upper == "/UNINSTALL")
            {
                options.Uninstall = true;
            }
            else if (upper == "/NODESKTOP")
            {
                options.DesktopIcon = false;
            }
            else if (upper == "/LAUNCH")
            {
                options.LaunchAfter = true;
            }
            else if (upper == "/NOLAUNCH")
            {
                options.LaunchAfter = false;
            }
            else if (StartsWith(arg, "/DIR="))
            {
                options.InstallDir = arg.Substring(5).Trim('"');
            }
            else if (StartsWith(arg, "/MODELS="))
            {
                options.ModelsDir = arg.Substring(8).Trim('"');
            }
            else if (StartsWith(arg, "/PROJECTS="))
            {
                options.ProjectsDir = arg.Substring(10).Trim('"');
            }
            else if (StartsWith(arg, "/CACHE="))
            {
                options.CacheDir = arg.Substring(7).Trim('"');
            }
            else if (StartsWith(arg, "/UNINSTALLMODE="))
            {
                options.Uninstall = true;
                options.UninstallMode = arg.Substring(15).Trim('"');
                options.Silent = true;
            }
            else if (StartsWith(arg, "/TASKS="))
            {
                options.DesktopIcon = arg.IndexOf("desktopicon", StringComparison.OrdinalIgnoreCase) >= 0;
            }
        }
        return options;
    }

    private static bool StartsWith(string value, string prefix)
    {
        return value.StartsWith(prefix, StringComparison.OrdinalIgnoreCase);
    }
}

internal static class Payload
{
    public static void ExtractTo(string destDir, Action<int, int, string> progress)
    {
        string self = Application.ExecutablePath;
        long offset;
        long size;
        ReadFooter(self, out offset, out size);
        Directory.CreateDirectory(destDir);
        using (FileStream exe = File.OpenRead(self))
        using (SliceStream slice = new SliceStream(exe, offset, size))
        using (ZipArchive zip = new ZipArchive(slice, ZipArchiveMode.Read, false, Encoding.UTF8))
        {
            int total = Math.Max(zip.Entries.Count, 1);
            int index = 0;
            foreach (ZipArchiveEntry entry in zip.Entries)
            {
                index++;
                string relative = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                if (string.IsNullOrEmpty(relative))
                {
                    continue;
                }
                string full = Path.GetFullPath(Path.Combine(destDir, relative));
                string root = Path.GetFullPath(destDir);
                if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidOperationException("安装包路径非法：" + entry.FullName);
                }
                if (progress != null)
                {
                    progress(index, total, relative);
                }
                if (relative.EndsWith(Path.DirectorySeparatorChar.ToString()) || string.IsNullOrEmpty(entry.Name))
                {
                    Directory.CreateDirectory(full);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(full));
                entry.ExtractToFile(full, true);
            }
        }
    }

    private static void ReadFooter(string exePath, out long offset, out long size)
    {
        using (FileStream stream = File.OpenRead(exePath))
        {
            if (stream.Length < 32)
            {
                throw new InvalidOperationException("安装包损坏：文件过小。");
            }
            stream.Seek(-32, SeekOrigin.End);
            byte[] footer = new byte[32];
            int read = stream.Read(footer, 0, 32);
            if (read != 32)
            {
                throw new InvalidOperationException("安装包损坏：无法读取尾部。");
            }
            string magic = Encoding.ASCII.GetString(footer, 16, 16);
            if (magic != Payload.MagicText())
            {
                throw new InvalidOperationException("安装包损坏：找不到程序文件。请重新下载 LocalVideoAI_Setup.exe 或 LocalVideoAI_Portable.exe。");
            }
            offset = BitConverter.ToInt64(footer, 0);
            size = BitConverter.ToInt64(footer, 8);
            if (offset < 0 || size < 1 || offset + size > stream.Length - 32)
            {
                throw new InvalidOperationException("安装包损坏：数据区无效。");
            }
        }
    }

    private static string MagicText()
    {
        return "LVAIPAYLOADV1.0!";
    }
}

internal sealed class SliceStream : Stream
{
    private readonly Stream _inner;
    private readonly long _start;
    private readonly long _length;
    private long _position;

    public SliceStream(Stream inner, long start, long length)
    {
        _inner = inner;
        _start = start;
        _length = length;
        _inner.Seek(start, SeekOrigin.Begin);
        _position = 0;
    }

    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return _length; } }
    public override long Position
    {
        get { return _position; }
        set { Seek(value, SeekOrigin.Begin); }
    }

    public override void Flush() { }

    public override int Read(byte[] buffer, int offset, int count)
    {
        long remain = _length - _position;
        if (remain <= 0)
        {
            return 0;
        }
        if (count > remain)
        {
            count = (int)remain;
        }
        int read = _inner.Read(buffer, offset, count);
        _position += read;
        return read;
    }

    public override long Seek(long offset, SeekOrigin origin)
    {
        long next = _position;
        if (origin == SeekOrigin.Begin)
        {
            next = offset;
        }
        else if (origin == SeekOrigin.Current)
        {
            next = _position + offset;
        }
        else if (origin == SeekOrigin.End)
        {
            next = _length + offset;
        }
        if (next < 0)
        {
            next = 0;
        }
        if (next > _length)
        {
            next = _length;
        }
        _inner.Seek(_start + next, SeekOrigin.Begin);
        _position = next;
        return _position;
    }

    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
}

internal static class Installer
{
    public static void RunSilent(Options options)
    {
        Run(options, null);
    }

    public static void Run(Options options, Action<int, int, string> progress)
    {
        string dest = Path.GetFullPath(options.InstallDir);
        Directory.CreateDirectory(dest);
        Payload.ExtractTo(dest, progress);
        if (options.Portable)
        {
            File.WriteAllText(Path.Combine(dest, "portable.flag"), "1\r\n", Encoding.UTF8);
        }
        else
        {
            Directory.CreateDirectory(options.ModelsDir);
            Directory.CreateDirectory(options.ProjectsDir);
            Directory.CreateDirectory(options.CacheDir);
            WriteInstallPaths(dest, options);
            CopyUninstaller(dest);
            Shortcuts.Create(dest, options.DesktopIcon);
            RegisterUninstall(dest);
        }
        if (options.LaunchAfter)
        {
            string exe = Path.Combine(dest, AppExeName());
            if (File.Exists(exe))
            {
                Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true, WorkingDirectory = dest });
            }
        }
    }

    private static string AppExeName()
    {
        return "LocalVideoAI.exe";
    }

    private static void WriteInstallPaths(string dest, Options options)
    {
        string json = string.Format(
            "{{\r\n  \"models_dir\": \"{0}\",\r\n  \"projects_dir\": \"{1}\",\r\n  \"cache_dir\": \"{2}\"\r\n}}\r\n",
            JsonEscape(options.ModelsDir),
            JsonEscape(options.ProjectsDir),
            JsonEscape(options.CacheDir));
        File.WriteAllText(Path.Combine(dest, "install_paths.json"), json, new UTF8Encoding(false));
    }

    private static string JsonEscape(string value)
    {
        return Path.GetFullPath(value).Replace("\\", "/").Replace("\"", "\\\"");
    }

    private static void CopyUninstaller(string dest)
    {
        string self = Application.ExecutablePath;
        using (FileStream stream = File.OpenRead(self))
        {
            if (stream.Length < 32)
            {
                return;
            }
            stream.Seek(-32, SeekOrigin.End);
            byte[] footer = new byte[32];
            stream.Read(footer, 0, 32);
            long offset = BitConverter.ToInt64(footer, 0);
            if (offset < 64)
            {
                return;
            }
            stream.Seek(0, SeekOrigin.Begin);
            byte[] stub = new byte[offset];
            int read = 0;
            while (read < stub.Length)
            {
                int n = stream.Read(stub, read, stub.Length - read);
                if (n <= 0)
                {
                    break;
                }
                read += n;
            }
            File.WriteAllBytes(Path.Combine(dest, "Uninstall.exe"), stub);
        }
    }

    private static void RegisterUninstall(string dest)
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(UninstallKeyName()))
        {
            if (key == null)
            {
                return;
            }
            string uninstall = Path.Combine(dest, "Uninstall.exe");
            key.SetValue("DisplayName", "LocalVideoAI Translator");
            key.SetValue("DisplayVersion", "0.22.4");
            key.SetValue("Publisher", "LocalVideoAI");
            key.SetValue("InstallLocation", dest);
            key.SetValue("DisplayIcon", Path.Combine(dest, "LocalVideoAI.exe"));
            key.SetValue("UninstallString", "\"" + uninstall + "\"");
            key.SetValue("QuietUninstallString", "\"" + uninstall + "\" /SILENT /UNINSTALLMODE=program");
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        }
    }

    private static string UninstallKeyName()
    {
        return @"Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalVideoAI";
    }
}

internal static class Shortcuts
{
    public static void Create(string dest, bool desktop)
    {
        string exe = Path.Combine(dest, "LocalVideoAI.exe");
        string uninstall = Path.Combine(dest, "Uninstall.exe");
        string startDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            "Programs",
            "LocalVideoAI Translator");
        Directory.CreateDirectory(startDir);
        CreateShortcut(Path.Combine(startDir, "LocalVideoAI Translator.lnk"), exe, dest);
        if (File.Exists(uninstall))
        {
            CreateShortcut(Path.Combine(startDir, "卸载 LocalVideoAI.lnk"), uninstall, dest);
        }
        if (desktop)
        {
            string desk = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "LocalVideoAI Translator.lnk");
            CreateShortcut(desk, exe, dest);
        }
    }

    public static void Remove()
    {
        TryDelete(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "LocalVideoAI Translator.lnk"));
        string startDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            "Programs",
            "LocalVideoAI Translator");
        TryDelete(Path.Combine(startDir, "LocalVideoAI Translator.lnk"));
        TryDelete(Path.Combine(startDir, "卸载 LocalVideoAI.lnk"));
        try
        {
            if (Directory.Exists(startDir) && Directory.GetFileSystemEntries(startDir).Length == 0)
            {
                Directory.Delete(startDir);
            }
        }
        catch
        {
        }
    }

    private static void CreateShortcut(string path, string target, string workDir)
    {
        Type type = Type.GetTypeFromProgID("WScript.Shell");
        if (type == null)
        {
            return;
        }
        object shell = Activator.CreateInstance(type);
        object shortcut = type.InvokeMember(
            "CreateShortcut",
            System.Reflection.BindingFlags.InvokeMethod,
            null,
            shell,
            new object[] { path });
        Type shortcutType = shortcut.GetType();
        shortcutType.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { target });
        shortcutType.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { workDir });
        shortcutType.InvokeMember("IconLocation", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { target });
        shortcutType.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, shortcut, null);
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
        }
    }
}

internal static class Uninstaller
{
    public static int Run(Options options)
    {
        string appDir = Path.GetDirectoryName(Application.ExecutablePath);
        string exe = Path.Combine(appDir, "LocalVideoAI.exe");
        if (!File.Exists(exe))
        {
            throw new InvalidOperationException("找不到 LocalVideoAI.exe，无法卸载。");
        }
        string args = options.Silent
            ? "--uninstall-mode " + SanitizeMode(options.UninstallMode)
            : "--uninstall";
        ProcessStartInfo info = new ProcessStartInfo(exe, args);
        info.UseShellExecute = false;
        info.WorkingDirectory = appDir;
        Process process = Process.Start(info);
        if (process == null)
        {
            throw new InvalidOperationException("无法启动卸载程序。");
        }
        process.WaitForExit();
        if (process.ExitCode != 0)
        {
            return process.ExitCode;
        }
        Shortcuts.Remove();
        try
        {
            Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalVideoAI");
        }
        catch
        {
        }
        string cmd = "/c ping 127.0.0.1 -n 2 >nul & rmdir /s /q \"" + appDir.Replace("\"", "") + "\"";
        Process.Start(new ProcessStartInfo("cmd.exe", cmd)
        {
            CreateNoWindow = true,
            UseShellExecute = false
        });
        return 0;
    }

    private static string SanitizeMode(string mode)
    {
        string key = (mode ?? "program").Trim().ToLowerInvariant();
        if (key == "keep_models" || key == "keep-models")
        {
            return "keep_models";
        }
        if (key == "keep_projects" || key == "keep-projects")
        {
            return "keep_projects";
        }
        if (key == "wipe" || key == "all" || key == "delete_all")
        {
            return "wipe";
        }
        return "program";
    }
}

internal sealed class WizardForm : Form
{
    private readonly Options _options;
    private readonly TextBox _dir;
    private readonly TextBox _models;
    private readonly TextBox _projects;
    private readonly TextBox _cache;
    private readonly CheckBox _desktop;
    private readonly CheckBox _launch;
    private readonly Button _ok;
    private readonly Label _status;
    private readonly ProgressBar _bar;

    public WizardForm(Options options)
    {
        _options = options;
        Text = options.Portable ? "LocalVideoAI Translator 便携版" : "安装 LocalVideoAI Translator";
        Width = 620;
        Height = options.Portable ? 360 : 520;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Microsoft YaHei UI", 9F);

        int y = 16;
        Controls.Add(MakeLabel(options.Portable
            ? "解压后可直接双击 LocalVideoAI.exe 运行。不需要 Python、Node、FFmpeg 或开发工具。"
            : "选择安装目录和数据目录。不需要 Python、Node、FFmpeg 或开发工具。", y));
        y += 48;
        _dir = AddBrowseRow(options.Portable ? "解压目录" : "安装目录", options.InstallDir, ref y);
        if (!options.Portable)
        {
            _models = AddBrowseRow("模型目录", options.ModelsDir, ref y);
            _projects = AddBrowseRow("项目目录", options.ProjectsDir, ref y);
            _cache = AddBrowseRow("缓存目录", options.CacheDir, ref y);
            _desktop = new CheckBox();
            _desktop.Text = "创建桌面快捷方式";
            _desktop.Checked = options.DesktopIcon;
            _desktop.SetBounds(20, y, 280, 24);
            Controls.Add(_desktop);
            y += 28;
        }
        else
        {
            _models = _projects = _cache = null;
            _desktop = null;
        }
        _launch = new CheckBox();
        _launch.Text = "完成后立即启动";
        _launch.Checked = options.LaunchAfter;
        _launch.SetBounds(20, y, 280, 24);
        Controls.Add(_launch);
        y += 36;
        _bar = new ProgressBar();
        _bar.SetBounds(20, y, 560, 22);
        Controls.Add(_bar);
        y += 28;
        _status = MakeLabel("准备就绪。", y);
        y += 36;
        _ok = new Button();
        _ok.Text = options.Portable ? "解压并运行" : "安装";
        _ok.SetBounds(360, y, 100, 30);
        _ok.Click += OnInstall;
        Button cancel = new Button();
        cancel.Text = "取消";
        cancel.SetBounds(480, y, 100, 30);
        cancel.Click += delegate { Close(); };
        Controls.Add(_ok);
        Controls.Add(cancel);
    }

    private Label MakeLabel(string text, int y)
    {
        Label label = new Label();
        label.Text = text;
        label.SetBounds(20, y, 560, 40);
        Controls.Add(label);
        return label;
    }

    private TextBox AddBrowseRow(string title, string value, ref int y)
    {
        Label label = new Label();
        label.Text = title;
        label.SetBounds(20, y, 80, 24);
        Controls.Add(label);
        TextBox box = new TextBox();
        box.Text = value;
        box.SetBounds(110, y, 360, 24);
        Controls.Add(box);
        Button browse = new Button();
        browse.Text = "浏览";
        browse.SetBounds(480, y, 100, 24);
        TextBox captured = box;
        browse.Click += delegate
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.SelectedPath = captured.Text;
                dialog.Description = title;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    captured.Text = dialog.SelectedPath;
                }
            }
        };
        Controls.Add(browse);
        y += 36;
        return box;
    }

    private void OnInstall(object sender, EventArgs e)
    {
        _ok.Enabled = false;
        try
        {
            _options.InstallDir = _dir.Text.Trim();
            if (!_options.Portable)
            {
                _options.ModelsDir = _models.Text.Trim();
                _options.ProjectsDir = _projects.Text.Trim();
                _options.CacheDir = _cache.Text.Trim();
                _options.DesktopIcon = _desktop.Checked;
            }
            _options.LaunchAfter = _launch.Checked;
            Installer.Run(_options, delegate(int current, int total, string name)
            {
                _bar.Maximum = Math.Max(total, 1);
                _bar.Value = Math.Min(current, _bar.Maximum);
                _status.Text = "正在写入 " + name;
                Application.DoEvents();
            });
            _status.Text = _options.Portable ? "解压完成，可直接运行。" : "安装完成。";
            MessageBox.Show(_status.Text, Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            Close();
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            _ok.Enabled = true;
        }
    }
}
