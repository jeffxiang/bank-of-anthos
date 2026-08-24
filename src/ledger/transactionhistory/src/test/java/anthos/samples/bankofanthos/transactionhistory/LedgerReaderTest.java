/*
 * Copyright 2020, Google LLC.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package anthos.samples.bankofanthos.transactionhistory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.mockito.MockitoAnnotations.initMocks;

import java.util.Collections;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.web.client.ResourceAccessException;

class LedgerReaderTest {

    private LedgerReader ledgerReader;

    @Mock
    private TransactionRepository dbRepo;
    @Mock
    private LedgerReaderCallback callback;

    private static final String LOCAL_ROUTING_NUM = "123456789";
    private static final String ACCOUNT_NUM = "1234567890";
    private static final int POLL_MS = 5;
    private static final int LONG_POLL_MS = 5000;
    private static final long AWAIT_SECONDS = 10;

    @BeforeEach
    void setUp() {
        initMocks(this);
        ledgerReader = new LedgerReader();
        TestUtil.setField(ledgerReader, "dbRepo", dbRepo);
        TestUtil.setField(ledgerReader, "pollMs", POLL_MS);
        TestUtil.setField(ledgerReader, "localRoutingNum", LOCAL_ROUTING_NUM);
    }

    @Test
    @DisplayName("Given a null callback, refuse to start the reader")
    void startWithCallbackFailsWhenCallbackIsNull() {
        // When / Then
        assertThrows(IllegalStateException.class,
            () -> ledgerReader.startWithCallback(null));
        verifyNoInteractions(dbRepo);
    }

    @Test
    @DisplayName("Given the reader was never started, report it as alive")
    void isAliveWhenReaderNotStarted() {
        // When / Then
        assertTrue(ledgerReader.isAlive());
    }

    @Test
    @DisplayName("Given new transactions in the ledger, invoke the callback for each one")
    void startWithCallbackProcessesNewTransactions() throws Exception {
        // Given
        final Transaction transaction = TestUtil.newTransaction(2L,
            ACCOUNT_NUM, LOCAL_ROUTING_NUM, ACCOUNT_NUM, LOCAL_ROUTING_NUM, 10);
        // 0 at init, 2 signals new work, then 1 forces the thread to stop.
        when(dbRepo.latestTransactionId()).thenReturn(0L, 2L, 1L);
        when(dbRepo.findLatest(0L)).thenReturn(List.of(transaction));
        final List<Transaction> processed = new CopyOnWriteArrayList<>();

        // When
        ledgerReader.startWithCallback(processed::add);
        awaitDeath();

        // Then
        assertEquals(List.of(transaction), processed);
    }

    @Test
    @DisplayName("Given an empty ledger, start from the beginning without processing transactions")
    void startWithCallbackHandlesEmptyLedger() throws Exception {
        // Given
        // No transactions at init, then an id below the starting id stops the thread.
        when(dbRepo.latestTransactionId()).thenReturn(null, -2L);

        // When
        ledgerReader.startWithCallback(callback);
        awaitDeath();

        // Then
        verifyNoInteractions(callback);
    }

    @Test
    @DisplayName("Given the ledger database is unreachable at init, keep polling")
    void startWithCallbackSurvivesDatabaseErrorAtInit() throws Exception {
        // Given
        when(dbRepo.latestTransactionId())
            .thenThrow(new ResourceAccessException("db unreachable"))
            .thenReturn(-2L);

        // When
        ledgerReader.startWithCallback(callback);
        awaitDeath();

        // Then
        verifyNoInteractions(callback);
    }

    @Test
    @DisplayName("Given the ledger database is unreachable while polling, retry with the known id")
    void startWithCallbackSurvivesDatabaseErrorWhilePolling() throws Exception {
        // Given
        when(dbRepo.latestTransactionId())
            .thenReturn(5L)
            .thenThrow(new DataAccessResourceFailureException("db unreachable"))
            .thenReturn(1L);

        // When
        ledgerReader.startWithCallback(callback);
        awaitDeath();

        // Then
        verify(dbRepo, never()).findLatest(5L);
        verifyNoInteractions(callback);
    }

    @Test
    @DisplayName("Given the ledger is out of sync with the reader, stop the background thread")
    void isAliveIsFalseWhenLedgerIsOutOfSync() throws Exception {
        // Given
        when(dbRepo.latestTransactionId()).thenReturn(5L, 1L);
        when(dbRepo.findLatest(5L)).thenReturn(Collections.emptyList());

        // When
        ledgerReader.startWithCallback(callback);
        awaitDeath();

        // Then
        assertFalse(ledgerReader.isAlive());
    }

    @Test
    @DisplayName("Given the poll sleep is interrupted, keep polling the ledger")
    void startWithCallbackSurvivesInterruptedPollSleep() throws Exception {
        // Given
        TestUtil.setField(ledgerReader, "pollMs", LONG_POLL_MS);
        when(dbRepo.latestTransactionId()).thenReturn(5L, 1L);

        // When
        ledgerReader.startWithCallback(callback);
        ((Thread) TestUtil.getField(ledgerReader, "backgroundThread"))
            .interrupt();
        awaitDeath();

        // Then
        verifyNoInteractions(callback);
    }

    /**
     * Waits for the reader's background thread to terminate.
     *
     * Every test drives the mocked repository into the "out of sync" state,
     * which is the only way the thread exits its polling loop.
     */
    private void awaitDeath() throws InterruptedException {
        final long deadline = System.nanoTime()
            + TimeUnit.SECONDS.toNanos(AWAIT_SECONDS);
        while (ledgerReader.isAlive() && System.nanoTime() < deadline) {
            Thread.sleep(POLL_MS);
        }
        assertFalse(ledgerReader.isAlive(), "background thread still running");
    }
}
