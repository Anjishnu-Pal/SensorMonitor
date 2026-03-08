package com.sensormonitor.android

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView

/**
 * Requirement 7 — RecyclerView adapter for the Data tab.
 *
 * Uses ListAdapter + DiffUtil.ItemCallback for efficient, animated diffing.
 * Only the rows that actually changed (new at the bottom) are redrawn rather
 * than the whole list — critical for smooth live updates while the polling
 * loop fires every 2 seconds.
 */
class SensorReadingAdapter :
    ListAdapter<SensorReading, SensorReadingAdapter.ViewHolder>(DiffCallback()) {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val tvTimestamp: TextView = view.findViewById(R.id.tv_timestamp)
        val tvValues:    TextView = view.findViewById(R.id.tv_values)
        val tvTagId:     TextView = view.findViewById(R.id.tv_tag_id)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder =
        ViewHolder(
            LayoutInflater.from(parent.context)
                .inflate(R.layout.item_reading, parent, false)
        )

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = getItem(position)
        holder.tvTimestamp.text = item.timestamp
        holder.tvValues.text    = "Temp: %.1f °C  |  pH: %.2f  |  Glu: %.0f mg/dL"
            .format(item.temperature, item.ph, item.glucose)
        holder.tvTagId.text     = if (item.tagId.isNotBlank()) "Tag: ${item.tagId}" else ""
    }

    private class DiffCallback : DiffUtil.ItemCallback<SensorReading>() {
        override fun areItemsTheSame(old: SensorReading, new: SensorReading): Boolean =
            old.timestamp == new.timestamp && old.tagId == new.tagId
        override fun areContentsTheSame(old: SensorReading, new: SensorReading): Boolean =
            old == new
    }
}
