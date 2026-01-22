#!/usr/bin/env python3
"""Generate protobuf Python files for all versions."""
import subprocess
import sys
from pathlib import Path


def generate_version(version: str) -> bool:
    """Generate proto files for a specific version."""
    base_dir = Path(__file__).parent.parent
    proto_dir = base_dir / "proto" / version
    output_dir = base_dir / "walstream_proto" / version

    proto_file = proto_dir / "walstream.proto"

    if not proto_file.exists():
        print(f"Warning: {proto_file} not found, skipping {version}")
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        str(proto_file),
    ]

    print(f"Generating {version}: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error generating {version}:")
        print(f"  stdout: {result.stdout}")
        print(f"  stderr: {result.stderr}")
        return False

    # Fix relative imports in generated grpc file
    grpc_file = output_dir / "walstream_pb2_grpc.py"
    if grpc_file.exists():
        content = grpc_file.read_text()
        content = content.replace(
            "import walstream_pb2", "from . import walstream_pb2"
        )
        grpc_file.write_text(content)

    print(f"Generated {version} successfully")
    return True


def main() -> None:
    """Generate all proto versions."""
    base_dir = Path(__file__).parent.parent
    proto_base = base_dir / "proto"

    if not proto_base.exists():
        print(f"Error: Proto directory not found: {proto_base}")
        sys.exit(1)

    versions = [d.name for d in proto_base.iterdir() if d.is_dir()]

    if not versions:
        print("No version directories found in proto/")
        sys.exit(1)

    print(f"Found versions: {versions}")

    results = [generate_version(v) for v in sorted(versions)]

    if all(results):
        print("\nProto generation complete!")
    else:
        print("\nSome versions failed to generate")
        sys.exit(1)


if __name__ == "__main__":
    main()
