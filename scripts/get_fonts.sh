#!/usr/bin/env bash
# تنزيل خط Tajawal العربي (مرخّص OFL) لاستخدامه في الترجمة والصورة المصغرة
set -e
mkdir -p fonts
for f in Tajawal-Bold Tajawal-Medium; do
  [ -s "fonts/$f.ttf" ] || curl -sfL -o "fonts/$f.ttf" "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/$f.ttf"
done
