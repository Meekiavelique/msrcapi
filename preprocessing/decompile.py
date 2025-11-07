import asyncio
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

    async def decompile_version(
        self, version_id: str, jar_path: Path, mappings_path: Optional[Path] = None
    ) -> Path:
        """Decompile a Minecraft version"""
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

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                print(f"  Error decompiling {version_id}:")
                print(f"  STDOUT: {stdout.decode()}")
                print(f"  STDERR: {stderr.decode()}")
                raise Exception(f"Decompilation failed with code {process.returncode}")

            print(f"  Decompilation complete: {output_dir}")
            return output_dir

        except Exception as e:
            print(f"  Failed to decompile {version_id}: {e}")
            raise

    def count_files(self, output_dir: Path) -> int:
        return len(list(output_dir.rglob("*.java")))

    def get_directory_size(self, output_dir: Path) -> int:
        total = 0
        for file in output_dir.rglob("*"):
            if file.is_file():
                total += file.stat().st_size
        return total

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
    from pathlib import Path

    decompiler_jar = Path("./MinecraftDecompiler.jar")
    data_dir = Path("./data/minecraft")

    if not decompiler_jar.exists():
        print(f"Decompiler JAR not found: {decompiler_jar}")
        print("Please download from:")
        print("https://github.com/MaxPixelStudios/MinecraftDecompiler/releases")
        return

    decompiler = MinecraftDecompiler(decompiler_jar, data_dir)

    test_version = "1.20.1"
    jar_path = data_dir / test_version / f"{test_version}.jar"
    mappings_path = data_dir / test_version / "client.txt"

    if not jar_path.exists():
        print(f"JAR not found: {jar_path}")
        return

    await decompiler.decompile_version(test_version, jar_path, mappings_path)


if __name__ == "__main__":
    asyncio.run(main())
