import asyncio
import os
import platform
import shutil
import tarfile
import urllib.request
from pathlib import Path
from typing import Optional


class MinecraftDecompiler:
    def __init__(
        self,
        decompiler_jar: Path,
        data_dir: Path,
        decompiler_type: str = "fernflower",
        threads: int = 8,
        regenerate_vars: bool = True,
    ):
        self.decompiler_jar = decompiler_jar
        self.data_dir = data_dir
        self.decompiler_type = decompiler_type
        self.threads = threads
        self.regenerate_vars = regenerate_vars

        self.java_path = self.ensure_java()
        print(f"[OK] Using Java at: {self.java_path}")

    def ensure_java(self) -> str:
        """Ensure Java is installed and available in PATH."""
        java_exec = shutil.which("java")
        if java_exec:
            print("[INFO] Java already present.")
            return java_exec

        print("[INFO] Java not found. Installing OpenJDK 21.0.9 locally...")

        jdk_dir = Path("./runtime/java")
        tmp_dir = jdk_dir / "tmp_extract"
        archive_path = jdk_dir / "openjdk.tar.gz"

        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            arch = "x64"
        elif machine in ("aarch64", "arm64"):
            arch = "aarch64"
        elif machine in ("ppc64le",):
            arch = "ppc64le"
        else:
            raise EnvironmentError(f"Unsupported architecture: {machine}")

        is_alpine = os.path.exists("/etc/alpine-release")
        os_type = "alpine-linux" if is_alpine else "linux"

        print(f"[INFO] Detected architecture: {machine} -> {arch}")
        print(f"[INFO] Detected OS type: {os_type}")

        url = (
            f"https://github.com/adoptium/temurin21-binaries/releases/download/"
            f"jdk-21.0.9%2B10/OpenJDK21U-jre_{arch}_{os_type}_hotspot_21.0.9_10.tar.gz"
        )

        jdk_dir.mkdir(parents=True, exist_ok=True)

        print(f"[DOWNLOAD] Fetching {url}")
        urllib.request.urlretrieve(url, archive_path)

        print(f"[EXTRACT] Extracting safely to {tmp_dir}")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(tmp_dir, filter="data")

        extracted_folders = [p for p in tmp_dir.iterdir() if p.is_dir()]
        if not extracted_folders:
            raise EnvironmentError("No folder found inside the JRE archive.")
        extracted_root = extracted_folders[0]

        final_path = jdk_dir / extracted_root.name
        if final_path.exists():
            shutil.rmtree(final_path, ignore_errors=True)
        shutil.move(str(extracted_root), str(final_path))

        shutil.rmtree(tmp_dir, ignore_errors=True)
        archive_path.unlink(missing_ok=True)

        for root, dirs, files in os.walk(final_path):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
            for f in files:
                file_path = os.path.join(root, f)
                if "/bin/" in root or root.endswith("/bin"):
                    os.chmod(file_path, 0o755)
                else:
                    os.chmod(file_path, 0o644)

        bin_java = None
        for path in final_path.rglob("bin/java"):
            bin_java = path
            break

        if not bin_java or not bin_java.exists():
            raise EnvironmentError("Java binary not found in extracted JRE package.")

        os.environ["PATH"] = f"{bin_java.parent}:{os.environ['PATH']}"
        java_exec = shutil.which("java")
        if not java_exec:
            raise EnvironmentError("Failed to detect Java runtime after install.")

        print(f"[OK] Java installed at: {bin_java}")
        return java_exec


    async def decompile_version(
        self, version_id: str, jar_path: Path, mappings_path: Optional[Path] = None
    ) -> Path:
        print(f"\nDecompiling {version_id}...")

        version_dir = self.data_dir / version_id
        output_dir = version_dir / "src"
        mapped_output = version_dir / f"{version_id}-mapped.jar"

        if output_dir.exists() and output_dir.is_file():
            output_dir.unlink()

        if output_dir.exists() and any(output_dir.rglob("*.java")):
            print(f"  Already decompiled: {output_dir}")
            return output_dir

        cmd = [
            "java",
            "-jar",
            str(self.decompiler_jar),
            "-i",
            str(jar_path),
            "-o",
            str(mapped_output),
            "--decompiled-output",
            str(output_dir),
            "-d",
            self.decompiler_type,
            "-t",
            str(self.threads),
        ]

        if mappings_path and mappings_path.exists():
            cmd.extend(["-m", str(mappings_path)])
            print(f"  Using mappings: {mappings_path}")

        if self.regenerate_vars:
            cmd.append("--regenerate-variable-names")

        print(f"  Running: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        stdout_text = stdout.decode(errors="ignore").strip()
        stderr_text = stderr.decode(errors="ignore").strip()

        if stdout_text:
            print(f"  [STDOUT]:\n{stdout_text}")
        if stderr_text:
            print(f"  [STDERR]:\n{stderr_text}")

        if process.returncode != 0:
            print(f"  Error: Decompilation failed with code {process.returncode}")
            raise RuntimeError(f"Decompilation failed with code {process.returncode}")

        java_files = list(output_dir.rglob("*.java")) if output_dir.exists() else []
        if not java_files:
            print(f"  Warning: No .java files found in {output_dir}")
        else:
            print(f"  Success: Created {len(java_files)} .java files")

        print(f"  Decompilation complete: {output_dir}")
        return output_dir

    def count_files(self, output_dir: Path) -> int:
        return len(list(output_dir.rglob("*.java")))

    def get_directory_size(self, output_dir: Path) -> int:
        return sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())

    async def decompile_all(
        self, versions: list[tuple[str, Path, Optional[Path]]]
    ) -> list[tuple[str, Path, int, int]]:
        results = []
        for version_id, jar_path, mappings_path in versions:
            try:
                output_dir = await self.decompile_version(version_id, jar_path, mappings_path)
                file_count = self.count_files(output_dir)
                size_bytes = self.get_directory_size(output_dir)
                print(f"  Files: {file_count}, Size: {size_bytes / 1024 / 1024:.2f} MB")
                results.append((version_id, output_dir, file_count, size_bytes))
            except Exception as e:
                print(f"Failed to decompile {version_id}: {e}")
        return results


async def main():
    decompiler_jar = Path("./MinecraftDecompiler.jar")
    data_dir = Path("./data/minecraft")

    if not decompiler_jar.exists():
        print(f"Decompiler JAR not found: {decompiler_jar}")
        print("Please download from:")
        print("https://github.com/MaxPixelStudios/MinecraftDecompiler/releases")
        return

    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return

    decompiler = MinecraftDecompiler(decompiler_jar, data_dir)


    versions = []
    for version_dir in sorted(data_dir.iterdir()):
        if not version_dir.is_dir():
            continue

        version_id = version_dir.name
        jar_path = version_dir / f"{version_id}.jar"
        mappings_path = version_dir / "client.txt"

        if jar_path.exists():
            if not mappings_path.exists():
                mappings_path = None
            versions.append((version_id, jar_path, mappings_path))
            print(f"[FOUND] {version_id}")
        else:
            print(f"[SKIP] {version_id} (no JAR file)")

    if not versions:
        print("No versions found to decompile")
        return

    print(f"\n[INFO] Found {len(versions)} version(s) to decompile\n")

    results = await decompiler.decompile_all(versions)

    print(f"\n[COMPLETE] Decompiled {len(results)}/{len(versions)} version(s)")


if __name__ == "__main__":
    asyncio.run(main())
