package com.sensormonitor.android

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.launch

/**
 * Requirement 7 — Tab 1: Data View (scrolling RecyclerView).
 *
 * Requirement 6 fix — instant UI sync:
 *   Collects from NfcViewModel.sensorReadings StateFlow using
 *   repeatOnLifecycle(STARTED). The moment NfcSensorManager calls
 *   viewModel.addReading() on the Main dispatcher, this collector runs
 *   synchronously in the same coroutine frame → adapter.submitList() is
 *   called → DiffUtil calculates the minimal diff → RecyclerView appends
 *   the new row with an animated insert — all within ~16 ms.
 *
 * The ViewModel is shared (activityViewModels) so this fragment and
 * GraphFragment both react to the SAME StateFlow emission. Neither tab
 * needs to poll CSV or maintain its own state.
 */
class DataFragment : Fragment() {

    private val viewModel: NfcViewModel by activityViewModels()
    private lateinit var adapter: SensorReadingAdapter

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_data, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        val recyclerView: RecyclerView = view.findViewById(R.id.recyclerView)
        val tvEmpty: TextView          = view.findViewById(R.id.tv_empty)

        adapter = SensorReadingAdapter()
        recyclerView.layoutManager = LinearLayoutManager(requireContext())
        recyclerView.adapter = adapter

        // Requirement 6: collect StateFlow — instant UI refresh on new data
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.sensorReadings.collect { readings ->
                    adapter.submitList(readings.toList())

                    // Toggle empty-state label
                    if (readings.isEmpty()) {
                        tvEmpty.visibility     = View.VISIBLE
                        recyclerView.visibility = View.GONE
                    } else {
                        tvEmpty.visibility     = View.GONE
                        recyclerView.visibility = View.VISIBLE
                        // Auto-scroll to the latest row
                        recyclerView.scrollToPosition(readings.size - 1)
                    }
                }
            }
        }
    }
}
