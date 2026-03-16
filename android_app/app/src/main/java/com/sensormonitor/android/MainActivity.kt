package com.sensormonitor.android

import android.app.PendingIntent
import android.content.Intent
import android.content.IntentFilter
import android.nfc.NdefMessage
import android.nfc.NfcAdapter
import android.nfc.NfcManager
import android.nfc.Tag
import android.nfc.tech.IsoDep
import android.nfc.tech.Ndef
import android.nfc.tech.NfcA
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.viewpager2.widget.ViewPager2
import com.google.android.material.tabs.TabLayout
import com.google.android.material.tabs.TabLayoutMediator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Requirements 1 + 2 + 3 + 6 + 7 — Main Activity.
 *
 * Responsibilities
 * ────────────────
 * Req 1  NFC adapter check and NFC-off prompt.
 * Req 2  FLAG_MUTABLE PendingIntent; enable/disable foreground dispatch in
 *        onResume()/onPause() strictly following the Android lifecycle.
 * Req 3  handleIntent() extracts NDEF messages with the modern, type-safe
 *        Build.VERSION_CODES.TIRAMISU / deprecated-fallback pattern, then
 *        hands Tag objects to NfcSensorManager.
 * Req 6  Observes NfcViewModel.connectionStatus (StateFlow) with
 *        repeatOnLifecycle(STARTED) so the status bar always shows current state.
 * Req 7  Hosts TabLayout + ViewPager2 with DataFragment (tab 0) and
 *        GraphFragment (tab 1).
 */
class MainActivity : AppCompatActivity() {

    private val TAG = "MainActivity"

    // ── NFC ───────────────────────────────────────────────────────────────────
    private var nfcAdapter: NfcAdapter? = null
    private lateinit var nfcPendingIntent: PendingIntent
    private lateinit var intentFilters: Array<IntentFilter>
    private lateinit var techLists: Array<Array<String>>

    // ── Services ──────────────────────────────────────────────────────────────
    private val viewModel: NfcViewModel by viewModels()
    private lateinit var csvHandler: CsvHandler
    private lateinit var nfcSensorManager: NfcSensorManager

    // ── UI ────────────────────────────────────────────────────────────────────
    private lateinit var tvStatus: TextView

    // ─────────────────────────────────────────────────────────────────────────

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // ── Services ──────────────────────────────────────────────────────────
        csvHandler = CsvHandler(this)
        nfcSensorManager = NfcSensorManager(
            csvHandler         = csvHandler,
            onReadingReceived  = { reading -> viewModel.addReading(reading) },
            onConnectionLost   = { viewModel.setDisconnected() }
        )

        // ── Requirement 1: NFC adapter existence + enabled check ──────────────
        val nfcManager = getSystemService(NfcManager::class.java)
        nfcAdapter = nfcManager?.defaultAdapter

        if (nfcAdapter == null) {
            Toast.makeText(this,
                getString(R.string.nfc_not_supported), Toast.LENGTH_LONG).show()
            finish()
            return
        }

        if (nfcAdapter?.isEnabled == false) {
            // Inform and redirect — do not block the app completely.
            Toast.makeText(this,
                getString(R.string.nfc_disabled), Toast.LENGTH_LONG).show()
            startActivity(Intent(Settings.ACTION_NFC_SETTINGS))
        }

        // ── Requirement 2: Foreground dispatch setup ──────────────────────────
        setupForegroundDispatch()

        // ── UI ────────────────────────────────────────────────────────────────
        tvStatus = findViewById(R.id.tv_status)

        // Requirement 7: TabLayout + ViewPager2
        val viewPager: ViewPager2 = findViewById(R.id.viewPager)
        val tabLayout: TabLayout  = findViewById(R.id.tabLayout)

        viewPager.adapter = ViewPagerAdapter(this)
        TabLayoutMediator(tabLayout, viewPager) { tab, pos ->
            tab.text = when (pos) {
                0    -> getString(R.string.tab_data)
                1    -> getString(R.string.tab_graphs)
                else -> "Tab $pos"
            }
        }.attach()

        // ── Requirement 6: Observe connectionStatus StateFlow ─────────────────
        // repeatOnLifecycle(STARTED) automatically starts/stops collection
        // when the Activity is visible — no manual cancel needed.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.connectionStatus.collect { status ->
                    tvStatus.text = status
                    // Colour the status bar to reflect connection state
                    val colour = when {
                        "connected" in status.lowercase() -> getColor(R.color.colorStatusConnected)
                        "out of range" in status          -> getColor(R.color.colorStatusLost)
                        else                              -> getColor(R.color.colorStatusWaiting)
                    }
                    tvStatus.setTextColor(colour)
                }
            }
        }

        // ── Pre-load historical CSV data (Dispatchers.IO — no ANR risk) ───────
        lifecycleScope.launch {
            val historical = withContext(Dispatchers.IO) { csvHandler.loadAll() }
            viewModel.loadReadings(historical)
            Log.i(TAG, "Loaded ${historical.size} historical rows from CSV")
        }

        // If the app was cold-started by an NFC tap, handle that intent now.
        handleIntent(intent)
    }

    // ── Requirement 2: FLAG_MUTABLE PendingIntent ──────────────────────────────
    private fun setupForegroundDispatch() {
        val nfcIntent = Intent(this, javaClass)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)

        // Android 12 (API 31) mandates an explicit mutability flag on all
        // PendingIntents. NFC foreground dispatch MUST use FLAG_MUTABLE because
        // the NFC subsystem fills in discovered-tag extras at delivery time.
        // Since minSdk = 31, FLAG_MUTABLE is always available — no version guard.
        nfcPendingIntent = PendingIntent.getActivity(
            this, 0, nfcIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        )

        // Intent filters for enableForegroundDispatch:
        //   NDEF with text/plain MIME (NHS 3152 text records — Requirement 1)
        //   TECH & TAG as catch-alls
        val ndefFilter = IntentFilter(NfcAdapter.ACTION_NDEF_DISCOVERED).also {
            try { it.addDataType("text/plain") }
            catch (e: IntentFilter.MalformedMimeTypeException) {
                Log.e(TAG, "Bad MIME: ${e.message}")
            }
        }
        intentFilters = arrayOf(
            ndefFilter,
            IntentFilter(NfcAdapter.ACTION_TECH_DISCOVERED),
            IntentFilter(NfcAdapter.ACTION_TAG_DISCOVERED)
        )

        // Tech whitelist: every combination the NHS 3152 can present
        techLists = arrayOf(
            arrayOf(Ndef::class.java.name),
            arrayOf(NfcA::class.java.name),
            arrayOf(IsoDep::class.java.name)
        )
    }

    // ── Requirement 2: enable in onResume ─────────────────────────────────────
    override fun onResume() {
        super.onResume()
        nfcAdapter?.enableForegroundDispatch(
            this, nfcPendingIntent, intentFilters, techLists
        )
        Log.i(TAG, "Foreground dispatch ENABLED")
    }

    // ── Requirement 2: disable in onPause ─────────────────────────────────────
    override fun onPause() {
        super.onPause()
        nfcAdapter?.disableForegroundDispatch(this)
        Log.i(TAG, "Foreground dispatch DISABLED")
    }

    // ── Requirement 3: onNewIntent delivers foreground-dispatch tags ──────────
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)      // keep getIntent() fresh so Fragments can access it
        handleIntent(intent)
    }

    /**
     * Requirement 3 — NDEF parsing and Tag extraction.
     *
     * 1. Uses the modern TIRAMISU type-safe overload of getParcelableArrayExtra
     *    for EXTRA_NDEF_MESSAGES, with a deprecated-but-safe fallback for
     *    API 31/32 (before TIRAMISU landed).
     * 2. Passes parsed NdefMessage(s) straight to NfcSensorManager for
     *    immediate CSV storage + ViewModel update.
     * 3. Passes the raw Tag object to NfcSensorManager.processTag() which
     *    starts the continuous NfcA background polling loop (Requirement 4).
     */
    private fun handleIntent(intent: Intent) {
        val action = intent.action ?: return
        if (action !in listOf(
                NfcAdapter.ACTION_NDEF_DISCOVERED,
                NfcAdapter.ACTION_TECH_DISCOVERED,
                NfcAdapter.ACTION_TAG_DISCOVERED)) return

        Log.i(TAG, "handleIntent: $action")
        viewModel.setStatus("NHS 3152 tag detected — reading…")

        // ── Extract NDEF messages (modern type-safe API path) ─────────────────
        val rawMessages: Array<out android.os.Parcelable>? =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                intent.getParcelableArrayExtra(
                    NfcAdapter.EXTRA_NDEF_MESSAGES, NdefMessage::class.java)
            } else {
                @Suppress("DEPRECATION")
                intent.getParcelableArrayExtra(NfcAdapter.EXTRA_NDEF_MESSAGES)
            }

        if (!rawMessages.isNullOrEmpty()) {
            Log.i(TAG, "Intent carries ${rawMessages.size} NDEF message(s)")
            for (raw in rawMessages) {
                val msg     = raw as NdefMessage
                val tagId   = extractTagId(intent)
                val reading = nfcSensorManager.parseNdefMessage(msg, tagId)
                if (reading != null) {
                    csvHandler.save(reading)
                    viewModel.addReading(reading)
                    Log.i(TAG, "NDEF reading: T=${reading.temperature} " +
                               "pH=${reading.ph} G=${reading.glucose}")
                    break
                }
            }
        }

        // ── Extract raw Tag for continuous NfcA polling (Requirement 4) ───────
        val tag: Tag? =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                intent.getParcelableExtra(NfcAdapter.EXTRA_TAG, Tag::class.java)
            } else {
                @Suppress("DEPRECATION")
                intent.getParcelableExtra(NfcAdapter.EXTRA_TAG)
            }

        tag?.let {
            Log.i(TAG, "Tag found — starting NfcA polling loop")
            nfcSensorManager.processTag(it)
        }
    }

    /** Extract the tag UID as an uppercase hex string from the intent. */
    private fun extractTagId(intent: Intent): String {
        val tag: Tag? =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                intent.getParcelableExtra(NfcAdapter.EXTRA_TAG, Tag::class.java)
            } else {
                @Suppress("DEPRECATION")
                intent.getParcelableExtra(NfcAdapter.EXTRA_TAG)
            }
        return tag?.id?.joinToString("") { "%02X".format(it) } ?: ""
    }

    override fun onDestroy() {
        super.onDestroy()
        nfcSensorManager.destroy()   // cancels the CoroutineScope — stops all polling
    }
}
