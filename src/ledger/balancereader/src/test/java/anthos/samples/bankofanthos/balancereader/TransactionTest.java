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

package anthos.samples.bankofanthos.balancereader;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class TransactionTest {

    private Transaction transaction;

    private static final long TRANSACTION_ID = 42L;
    private static final String FROM_ACCOUNT_NUM = "1234567890";
    private static final String FROM_ROUTING_NUM = "123456789";
    private static final String TO_ACCOUNT_NUM = "9876543210";
    private static final String TO_ROUTING_NUM = "987654321";
    private static final int AMOUNT = 12345;

    @BeforeEach
    void setUp() {
        transaction = TestUtil.newTransaction(TRANSACTION_ID,
            FROM_ACCOUNT_NUM, FROM_ROUTING_NUM,
            TO_ACCOUNT_NUM, TO_ROUTING_NUM, AMOUNT);
    }

    @Test
    @DisplayName("Given a transaction, expose the ledger fields unchanged")
    void gettersReturnLedgerFields() {
        // When / Then
        assertEquals(TRANSACTION_ID, transaction.getTransactionId());
        assertEquals(FROM_ACCOUNT_NUM, transaction.getFromAccountNum());
        assertEquals(FROM_ROUTING_NUM, transaction.getFromRoutingNum());
        assertEquals(TO_ACCOUNT_NUM, transaction.getToAccountNum());
        assertEquals(TO_ROUTING_NUM, transaction.getToRoutingNum());
        assertEquals(AMOUNT, transaction.getAmount());
    }

    @Test
    @DisplayName("Given an amount in cents, render it as dollars in the string form")
    void toStringRendersAmountInDollars() {
        // When
        final String actualResult = transaction.toString();

        // Then
        assertEquals("1234567890->$123.45->9876543210", actualResult);
    }
}
