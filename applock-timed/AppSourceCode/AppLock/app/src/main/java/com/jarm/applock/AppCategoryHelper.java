package com.jarm.applock;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Build;

// Discovers "social" apps without any hardcoded package list and without
// any network call. Most social/messaging apps declare
// android:appCategory="social" in their own manifest (this is the same
// metadata the Play Store and Digital Wellbeing itself use to group apps
// into categories) - we just read it back via PackageManager.
//
// This only works on API 26+ (category field was added in Android 8).
// On older devices, or for apps that never declared a category, this
// returns false - meaning worst case those apps only ever hit the 5 hour
// global cap, never the stricter 2 hour social cap. Good enough for a
// personal-use device; not meant to be exhaustive.
public class AppCategoryHelper {

    public static boolean isSocialApp(Context context, String packageName) {
        if (packageName == null) return false;
        try {
            PackageManager pm = context.getPackageManager();
            ApplicationInfo info = pm.getApplicationInfo(packageName, 0);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (info.category == ApplicationInfo.CATEGORY_SOCIAL) {
                    return true;
                }
            }
        } catch (Exception e) {
            // Unknown/uninstalled package - not social by default.
        }
        return false;
    }
}
