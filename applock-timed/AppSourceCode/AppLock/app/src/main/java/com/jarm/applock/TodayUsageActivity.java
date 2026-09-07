package com.jarm.applock;

import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import java.util.List;
import java.util.Map;

// "Today's Usage" screen - a lightweight, read-only view of the same
// UsageStatsManager data UsageCheckReceiver already has permission to read.
// Everything here runs once, when the screen opens: no background service,
// no periodic refresh, no listener left running after the activity closes.
// Closing this screen returns the app to exactly the battery profile it had
// before - this class adds a UI, not a background component.
public class TodayUsageActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.today_usage_activity);

        Map<String, Integer> minutesPerApp = UsageStatsHelper.getMinutesPerAppToday(this);
        int totalMinutes = UsageStatsHelper.totalMinutes(minutesPerApp);
        List<UsageStatsHelper.UsageBucket> buckets = UsageStatsHelper.topBucketsWithOther(this, minutesPerApp, 7);

        UsageRingView ring = findViewById(R.id.usage_ring);
        ring.setBuckets(buckets);

        TextView totalTimeText = findViewById(R.id.total_time_text);
        totalTimeText.setText(formatMinutes(totalMinutes));

        TextView unlockCountText = findViewById(R.id.unlock_count_text);
        unlockCountText.setText(String.valueOf(UnlockCounter.getTodayCount(this)));

        LinearLayout legendContainer = findViewById(R.id.legend_container);
        TextView emptyState = findViewById(R.id.empty_state_text);
        if (buckets.isEmpty()) {
            emptyState.setVisibility(android.view.View.VISIBLE);
        } else {
            for (int i = 0; i < buckets.size(); i++) {
                legendContainer.addView(buildLegendRow(buckets.get(i), UsageRingView.colorForIndex(i)));
            }
        }
    }

    private static String formatMinutes(int totalMinutes) {
        int hours = totalMinutes / 60;
        int minutes = totalMinutes % 60;
        if (hours > 0) {
            return hours + " hr, " + minutes + " min";
        }
        return minutes + " min";
    }

    // Built programmatically rather than via a RecyclerView adapter - matches
    // the rest of this app's existing style (SettingsActivity/OtherSettings
    // also build simple rows directly) rather than introducing a new pattern
    // for a short, non-scrolling-heavy list.
    private LinearLayout buildLegendRow(UsageStatsHelper.UsageBucket bucket, int color) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        int verticalPadding = dp(6);
        rowParams.topMargin = dp(2);
        row.setLayoutParams(rowParams);
        row.setPadding(0, verticalPadding, 0, verticalPadding);

        android.view.View dot = new android.view.View(this);
        LinearLayout.LayoutParams dotParams = new LinearLayout.LayoutParams(dp(12), dp(12));
        dotParams.rightMargin = dp(12);
        dot.setLayoutParams(dotParams);
        GradientDrawable dotShape = new GradientDrawable();
        dotShape.setShape(GradientDrawable.OVAL);
        dotShape.setColor(color);
        dot.setBackground(dotShape);
        row.addView(dot);

        TextView label = new TextView(this);
        label.setText(bucket.label);
        label.setTextSize(15f);
        LinearLayout.LayoutParams labelParams = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        label.setLayoutParams(labelParams);
        row.addView(label);

        TextView time = new TextView(this);
        time.setText(formatMinutes(bucket.minutes));
        time.setTextSize(15f);
        time.setAlpha(0.75f);
        row.addView(time);

        return row;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density);
    }
}
