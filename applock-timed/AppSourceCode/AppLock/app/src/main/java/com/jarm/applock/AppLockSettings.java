package com.jarm.applock;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.HashMap;
import java.util.Map;

public class AppLockSettings implements Serializable {

    // ---- original explicit lock/suspend/hide lists (untouched, still usable) ----
    private ArrayList<String> lockedapppackagenames = new ArrayList<String>();
    private ArrayList<String> suspendedapppackagenames = new ArrayList<String>();
    private ArrayList<String> hiddenapppackagenames = new ArrayList<String>();

    private ArrayList<String> lockedappnames = new ArrayList<String>();
    private ArrayList<String> suspendedappnames = new ArrayList<String>();
    private ArrayList<String> hiddenappnames = new ArrayList<String>();
    private String password;

    // ---- new: hardcoded daily-timer enforcement, driven by periodic UsageStatsManager checks ----
    // Every app shares a 5 hour daily budget. Apps detected as "social" (via
    // PackageManager's ApplicationInfo.category) additionally share a
    // stricter 2 hour budget of their own. Both are hardcoded on purpose:
    // no setter, no UI to change them.
    public static final int TOTAL_DAILY_LIMIT_MINUTES = 5 * 60;   // 5 hours, all apps combined
    public static final int SOCIAL_DAILY_LIMIT_MINUTES = 2 * 60;  // 2 hours, social apps combined
    public static final long CHECK_INTERVAL_MINUTES = 30;         // how often UsageCheckReceiver runs

    // Snapshot of "minutes used today" per package, as read directly from
    // UsageStatsManager on the last check - not accumulated by us, just
    // mirrored. Overwritten wholesale every check, which makes this
    // self-correcting: a missed check, a service restart, a killed process
    // can never cause drift, because we never trust our own running total,
    // we just re-ask the OS.
    private HashMap<String, Integer> minutesUsedTodayPerApp = new HashMap<String, Integer>();
    private int totalMinutesUsedToday = 0;
    private int socialMinutesUsedToday = 0;
    private long lastResetEpochDay = -1;

    public AppLockSettings() {
    }

    // YEAR*1000 + DAY_OF_YEAR - a simple, strictly-increasing "which day is
    // it" id using only java.util.Calendar (API 1+). Deliberately not
    // java.time.LocalDate: minSdk is 24 and java.time needs API 26+ without
    // core library desugaring, which this project doesn't have enabled -
    // LocalDate.now() would crash with NoClassDefFoundError on a real
    // API 24/25 device.
    private static long currentDayId() {
        Calendar cal = Calendar.getInstance();
        return cal.get(Calendar.YEAR) * 1000L + cal.get(Calendar.DAY_OF_YEAR);
    }

    public void rollOverIfNewDay() {
        long today = currentDayId();
        if (today != lastResetEpochDay) {
            lastResetEpochDay = today;
            totalMinutesUsedToday = 0;
            socialMinutesUsedToday = 0;
            minutesUsedTodayPerApp.clear();
        }
    }

    // Called once per periodic check with a fresh reading from
    // UsageStatsManager. socialPackages tells it which of those packages
    // count toward the stricter social budget too.
    public void syncUsageFromSystem(Map<String, Integer> minutesPerPackageToday, java.util.Set<String> socialPackages) {
        rollOverIfNewDay();
        minutesUsedTodayPerApp = new HashMap<String, Integer>(minutesPerPackageToday);
        int total = 0;
        int social = 0;
        for (Map.Entry<String, Integer> entry : minutesUsedTodayPerApp.entrySet()) {
            total += entry.getValue();
            if (socialPackages.contains(entry.getKey())) {
                social += entry.getValue();
            }
        }
        totalMinutesUsedToday = total;
        socialMinutesUsedToday = social;
    }

    public boolean isOverGlobalDailyLimit() {
        rollOverIfNewDay();
        return totalMinutesUsedToday >= TOTAL_DAILY_LIMIT_MINUTES;
    }

    public boolean isOverSocialDailyLimit() {
        rollOverIfNewDay();
        return socialMinutesUsedToday >= SOCIAL_DAILY_LIMIT_MINUTES;
    }

    public int getTotalMinutesUsedToday() {
        rollOverIfNewDay();
        return totalMinutesUsedToday;
    }

    public int getSocialMinutesUsedToday() {
        rollOverIfNewDay();
        return socialMinutesUsedToday;
    }

    public Map<String, Integer> getMinutesUsedTodayPerApp() {
        rollOverIfNewDay();
        return minutesUsedTodayPerApp;
    }

    // ---- original methods, unchanged ----
    public boolean isAppPackageNameLocked(String logentrywithpackagename) {
        for (String packagename :lockedapppackagenames) {
            if (logentrywithpackagename.contains(packagename)) {
                if (AccSrvForBootstrapAndLock.tempunlockedpackagenames.contains(packagename)) {
                return false;
                }
                else {
                    return true;
                }
                }
        }
        return false;
    }
    public String findPackageNameFromLogEntry(String logentrywithpackagename) {
        for (String packagename :lockedapppackagenames) {
            if (logentrywithpackagename.contains(packagename)) {
                    return packagename;
            }
        }
        return "nulll";
    }
    public void addLockedAppPackageName(String packagename) {
        lockedapppackagenames.add(packagename);
    }
    public void addLockedAppName(String appname) {
        lockedappnames.add(appname);
    }
    public void removeLockedAppPackageName(String packagename) {
        lockedapppackagenames.remove(lockedapppackagenames.indexOf(packagename));
    }
    public void removeLockedAppName(String appname) {
        lockedappnames.remove(lockedappnames.indexOf(appname));
    }
    public boolean isAppPackageNameSuspended(String packagename) {
        for (String packagenamee :suspendedapppackagenames) {
            if (packagenamee.contains(packagename)) {
                return true;
            }
        }
        return false;
    }
    public boolean isAppPackageNameHidden(String packagename) {
        for (String packagenamee :this.lockedapppackagenames) {
            if (packagenamee.contains(packagename)) {
                return true;
            }
        }
        return false;
    }
    public boolean isAppNameLocked(String stringtocheck) {
        for (String appname :this.lockedappnames) {
            if (stringtocheck.contains(appname)) {
                return true;
            }
        }
        return false;
    }
}
