/*
 * Copyright 2026, Google LLC.
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

package anthos.samples.bankofanthos.ledgerwriter;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class TransactionTest {

    private static final String FROM_ACCOUNT_NUM = "1234567890";
    private static final String FROM_ROUTING_NUM = "123456789";
    private static final String TO_ACCOUNT_NUM = "0987654321";
    private static final String TO_ROUTING_NUM = "987654321";
    private static final String REQUEST_UUID = "synthetic-request-uuid";
    private static final int AMOUNT = 3755;

    @Test
    @DisplayName("Given transaction JSON, expose its write-path fields")
    void gettersWhenTransactionIsDeserializedReturnFields() throws Exception {
        // Given
        String json = String.format(
                "{\"fromAccountNum\":\"%s\",\"fromRoutingNum\":\"%s\","
                + "\"toAccountNum\":\"%s\",\"toRoutingNum\":\"%s\","
                + "\"amount\":%d,\"uuid\":\"%s\"}",
                FROM_ACCOUNT_NUM, FROM_ROUTING_NUM, TO_ACCOUNT_NUM,
                TO_ROUTING_NUM, AMOUNT, REQUEST_UUID);

        // When
        Transaction transaction =
                new ObjectMapper().readValue(json, Transaction.class);

        // Then
        assertEquals(0, transaction.getTransactionId());
        assertEquals(FROM_ACCOUNT_NUM, transaction.getFromAccountNum());
        assertEquals(FROM_ROUTING_NUM, transaction.getFromRoutingNum());
        assertEquals(TO_ACCOUNT_NUM, transaction.getToAccountNum());
        assertEquals(TO_ROUTING_NUM, transaction.getToRoutingNum());
        assertEquals(AMOUNT, transaction.getAmount());
        assertEquals(REQUEST_UUID, transaction.getRequestUuid());
        assertEquals("1234567890->$37.55->0987654321",
                transaction.toString());
    }

    @Test
    @DisplayName("Given no request UUID, expose the idempotency key as empty")
    void getRequestUuidWhenUnsetReturnsEmptyString() {
        // Then
        assertEquals("", new Transaction().getRequestUuid());
    }
}
