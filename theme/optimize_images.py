#!/usr/bin/env python3
"""
Image Optimization Script for Helwan Plast
Optimizes PNG images for mobile 3G performance

Usage:
    python theme/optimize_images.py

Requirements:
    pip install Pillow

Author: Auto-Claude
Date: 2026-02-12
Task: Mobile Responsive Design - Subtask 5.2
"""

from PIL import Image
import os
import sys

def optimize_png(input_path, output_path, max_width=None, quality=95):
    """
    Optimize PNG image with optional resizing

    Args:
        input_path: Path to input image
        output_path: Path to save optimized image
        max_width: Maximum width (maintains aspect ratio)
        quality: PNG compression quality (1-100)

    Returns:
        dict: Optimization results with original_size, optimized_size, savings_percent
    """
    try:
        img = Image.open(input_path)
        original_size_kb = os.path.getsize(input_path) / 1024
        original_dimensions = img.size

        print(f"  Original: {original_dimensions[0]}x{original_dimensions[1]}, {original_size_kb:.1f}KB")

        # Resize if max_width specified
        if max_width and img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            print(f"  Resized to: {img.size[0]}x{img.size[1]}")

        # Convert RGBA to indexed if possible (reduces size)
        if img.mode == 'RGBA':
            # Check if alpha channel is actually used
            alpha = img.split()[-1]
            alpha_range = alpha.getextrema()

            if alpha_range == (255, 255):
                # No transparency, convert to RGB
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=None)
                img = rgb_img
                print(f"  Converted RGBA to RGB (no transparency)")
            else:
                print(f"  Kept RGBA (has transparency: {alpha_range})")

        # Optimize and save
        # Use optimize=True and specify quality for best compression
        img.save(output_path, 'PNG', optimize=True)

        # Report results
        optimized_size_kb = os.path.getsize(output_path) / 1024
        savings_percent = ((original_size_kb - optimized_size_kb) / original_size_kb) * 100

        print(f"  Optimized: {optimized_size_kb:.1f}KB")
        print(f"  Savings: {savings_percent:.1f}% ({original_size_kb - optimized_size_kb:.1f}KB)")

        return {
            'success': True,
            'original_size': original_size_kb,
            'optimized_size': optimized_size_kb,
            'savings_percent': savings_percent,
            'original_dimensions': original_dimensions,
            'new_dimensions': img.size
        }

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {'success': False, 'error': str(e)}

def main():
    """Optimize all logos in theme/assets"""

    # Check if Pillow is available
    try:
        import PIL
    except ImportError:
        print("❌ Error: Pillow is not installed")
        print("\nInstall with:")
        print("  pip install Pillow")
        print("  # or")
        print("  pip install --user Pillow")
        sys.exit(1)

    # Determine assets directory (handle being run from different locations)
    if os.path.exists('theme/assets'):
        assets_dir = 'theme/assets'
    elif os.path.exists('assets'):
        assets_dir = 'assets'
    elif os.path.exists('../assets'):
        assets_dir = '../assets'
    else:
        print("❌ Error: Cannot find theme/assets directory")
        print(f"Current directory: {os.getcwd()}")
        sys.exit(1)

    print("=" * 70)
    print("Helwan Plast - Image Optimization for Mobile Performance")
    print("=" * 70)
    print(f"Assets directory: {os.path.abspath(assets_dir)}")
    print()

    optimizations = [
        {
            'input': f'{assets_dir}/helwan_logo-logo.png',
            'output': f'{assets_dir}/helwan_logo-logo_optimized.png',
            'max_width': 400,
            'description': 'App logo (large)',
            'notes': 'Used in: LauncherForm, CalculatorForm, AdminPanel, app metadata'
        },
        {
            'input': f'{assets_dir}/flexo_logo.png',
            'output': f'{assets_dir}/flexo_logo_optimized.png',
            'max_width': 800,
            'description': 'Flexo header logo',
            'notes': 'Used in: standard-page.html header (very wide: 1303px)'
        }
    ]

    results = []
    total_original = 0
    total_optimized = 0

    for i, opt in enumerate(optimizations, 1):
        print(f"{i}. {opt['description']}")
        print("-" * 70)
        print(f"   {opt['notes']}")

        if not os.path.exists(opt['input']):
            print(f"  ⚠️  File not found: {opt['input']}")
            print()
            continue

        result = optimize_png(
            opt['input'],
            opt['output'],
            max_width=opt.get('max_width'),
            quality=95
        )

        if result['success']:
            total_original += result['original_size']
            total_optimized += result['optimized_size']
            print(f"  ✅ Saved to: {opt['output']}")
            results.append({**opt, **result})
        else:
            print(f"  ❌ Optimization failed")

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if results:
        print(f"Files optimized: {len(results)}")
        print(f"Total original size: {total_original:.1f}KB")
        print(f"Total optimized size: {total_optimized:.1f}KB")
        print(f"Total savings: {total_original - total_optimized:.1f}KB ({((total_original - total_optimized) / total_original * 100):.1f}%)")
        print()

        print("Optimization Details:")
        for r in results:
            print(f"  • {r['description']}: {r['original_dimensions']} → {r['new_dimensions']}, "
                  f"{r['original_size']:.1f}KB → {r['optimized_size']:.1f}KB ({r['savings_percent']:.1f}% saved)")
        print()

        print("=" * 70)
        print("NEXT STEPS")
        print("=" * 70)
        print("1. Review optimized images visually:")
        for r in results:
            print(f"   - Compare {r['input']} with {r['output']}")
        print()
        print("2. If satisfied with quality, backup originals and replace:")
        print(f"   cd {assets_dir}")
        for r in results:
            filename = os.path.basename(r['input'])
            print(f"   cp {filename} {filename}.original")
            print(f"   mv {os.path.basename(r['output'])} {filename}")
        print()
        print("3. Test all forms to verify images display correctly:")
        print("   - LoginForm (helwan_logo.png)")
        print("   - LauncherForm (helwan_logo-logo.png)")
        print("   - CalculatorForm (helwan_logo-logo.png)")
        print("   - QuotationPrintForm (helwan_logo.png in PDF)")
        print("   - ContractPrintForm (helwan_logo.png in PDF)")
        print("   - standard-page.html (both logos)")
        print()
        print("4. Run 3G performance test:")
        print("   - Open Chrome DevTools → Network tab")
        print("   - Set throttling to 'Slow 3G'")
        print("   - Disable cache")
        print("   - Reload page")
        print("   - Verify: Initial load < 5 seconds ✅")
        print()
        print("5. Commit changes:")
        print("   git add theme/assets/*.png")
        print("   git commit -m \"auto-claude: subtask-5-2 - Optimize images for mobile performance\"")

    else:
        print("❌ No images were optimized")
        print("Check that image files exist in the assets directory")

    print()
    print("=" * 70)

if __name__ == '__main__':
    main()
