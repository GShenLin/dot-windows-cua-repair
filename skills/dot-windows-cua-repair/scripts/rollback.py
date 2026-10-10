"""Preview rollback by default; --apply restores only matching owned files."""
import argparse
import json
from repair_files import restore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(restore(args.manifest, args.apply), indent=2))


if __name__ == '__main__':
    main()
