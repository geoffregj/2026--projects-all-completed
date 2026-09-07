package com.jarm.applock;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.View;

import java.util.ArrayList;
import java.util.List;

// Multi-segment ring chart, drawn once per layout/data change with a plain
// Canvas - no animation loop, no continuous invalidate(). It only redraws
// when the activity that hosts it is on screen and calls setBuckets(), so
// there's no ongoing CPU/battery cost from this view existing.
public class UsageRingView extends View {

    // Same palette family as Android's own Digital Wellbeing ring: one
    // saturated hue per segment, cycled if there are more segments than colors.
    private static final int[] PALETTE = {
            0xFF4E8CFF, // blue
            0xFFE05C4A, // red
            0xFFF2B33D, // amber
            0xFF3DBFA8, // teal
            0xFF9B6BD9, // purple
            0xFF3FBF6B, // green
            0xFFB7C23A, // olive
            0xFFE0894A, // orange
    };

    private final Paint segmentPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint trackPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF ringRect = new RectF();

    private List<UsageStatsHelper.UsageBucket> buckets = new ArrayList<>();
    private float strokeWidthDp = 22f;

    public UsageRingView(Context context) {
        super(context);
        init();
    }

    public UsageRingView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    private void init() {
        segmentPaint.setStyle(Paint.Style.STROKE);
        segmentPaint.setStrokeCap(Paint.Cap.ROUND);
        trackPaint.setStyle(Paint.Style.STROKE);
        trackPaint.setColor(withAlpha(Color.GRAY, 40));
    }

    private static int withAlpha(int color, int alpha) {
        return Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color));
    }

    public void setBuckets(List<UsageStatsHelper.UsageBucket> buckets) {
        this.buckets = buckets != null ? buckets : new ArrayList<>();
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);

        float strokeWidthPx = strokeWidthDp * getResources().getDisplayMetrics().density;
        segmentPaint.setStrokeWidth(strokeWidthPx);
        trackPaint.setStrokeWidth(strokeWidthPx);

        int size = Math.min(getWidth(), getHeight());
        float inset = strokeWidthPx / 2f + 4f;
        float left = (getWidth() - size) / 2f + inset;
        float top = (getHeight() - size) / 2f + inset;
        float right = (getWidth() + size) / 2f - inset;
        float bottom = (getHeight() + size) / 2f - inset;
        ringRect.set(left, top, right, bottom);

        // Faint full-circle track underneath, so a low-usage day still shows
        // the ring's shape instead of near-nothing.
        canvas.drawArc(ringRect, 0, 360, false, trackPaint);

        int total = 0;
        for (UsageStatsHelper.UsageBucket b : buckets) total += b.minutes;
        if (total <= 0) return;

        // Small visual gap between segments, same idea as the Digital
        // Wellbeing ring, so adjacent colors don't blur together.
        float gapDegrees = buckets.size() > 1 ? 3f : 0f;
        float startAngle = -90f; // 12 o'clock, matches the reference screenshot
        for (int i = 0; i < buckets.size(); i++) {
            UsageStatsHelper.UsageBucket b = buckets.get(i);
            float sweep = (b.minutes / (float) total) * 360f - gapDegrees;
            if (sweep < 0) sweep = 0;
            segmentPaint.setColor(PALETTE[i % PALETTE.length]);
            canvas.drawArc(ringRect, startAngle, sweep, false, segmentPaint);
            startAngle += (b.minutes / (float) total) * 360f;
        }
    }

    // Exposes the palette so the legend list below the ring can use the same
    // colors as the segments, without duplicating the palette array.
    public static int colorForIndex(int index) {
        return PALETTE[index % PALETTE.length];
    }
}
