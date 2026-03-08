package com.sensormonitor.android

import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.viewpager2.adapter.FragmentStateAdapter

/**
 * Requirement 7 — ViewPager2 adapter.
 * Supplies DataFragment (tab 0) and GraphFragment (tab 1).
 */
class ViewPagerAdapter(activity: FragmentActivity) : FragmentStateAdapter(activity) {
    override fun getItemCount(): Int = 2
    override fun createFragment(position: Int): Fragment = when (position) {
        0    -> DataFragment()
        1    -> GraphFragment()
        else -> DataFragment()
    }
}
