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

import java.lang.reflect.Field;
import java.util.Date;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class TransactionTest {

    @Test
    @DisplayName("Given populated fields, return values and formatted text")
    void gettersAndToStringReturnPopulatedTransactionValues() {
        // Given
        Transaction transaction = new Transaction();
        Date timestamp = new Date(123456789L);
        setField(transaction, "transactionId", 42L);
        setField(transaction, "fromAccountNum", "from");
        setField(transaction, "fromRoutingNum", "route-from");
        setField(transaction, "toAccountNum", "to");
        setField(transaction, "toRoutingNum", "route-to");
        setField(transaction, "amount", 1234);
        setField(transaction, "timestamp", timestamp);

        // When / Then
        assertEquals(42L, transaction.getTransactionId());
        assertEquals("from", transaction.getFromAccountNum());
        assertEquals("route-from", transaction.getFromRoutingNum());
        assertEquals("to", transaction.getToAccountNum());
        assertEquals("route-to", transaction.getToRoutingNum());
        assertEquals(1234, transaction.getAmount());
        assertEquals("from->$12.34->to", transaction.toString());
    }

    private static void setField(Object target, String name, Object value) {
        try {
            Field field = target.getClass().getDeclaredField(name);
            field.setAccessible(true);
            field.set(target, value);
        } catch (ReflectiveOperationException e) {
            throw new AssertionError(e);
        }
    }
}
