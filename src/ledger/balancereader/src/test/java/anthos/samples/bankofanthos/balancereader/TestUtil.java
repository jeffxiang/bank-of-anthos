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

import java.lang.reflect.Field;
import java.util.Date;

/**
 * Shared helpers for injecting values into package-private fields and for
 * building synthetic Transaction fixtures.
 */
final class TestUtil {

    private TestUtil() {
    }

    static void setField(Object target, String name, Object value) {
        try {
            Field field = target.getClass().getDeclaredField(name);
            field.setAccessible(true);
            field.set(target, value);
        } catch (NoSuchFieldException | IllegalAccessException e) {
            throw new IllegalStateException(e);
        }
    }

    static Object getField(Object target, String name) {
        try {
            Field field = target.getClass().getDeclaredField(name);
            field.setAccessible(true);
            return field.get(target);
        } catch (NoSuchFieldException | IllegalAccessException e) {
            throw new IllegalStateException(e);
        }
    }

    static Transaction newTransaction(long transactionId,
            String fromAccountNum,
            String fromRoutingNum,
            String toAccountNum,
            String toRoutingNum,
            int amount) {
        Transaction transaction = new Transaction();
        setField(transaction, "transactionId", transactionId);
        setField(transaction, "fromAccountNum", fromAccountNum);
        setField(transaction, "fromRoutingNum", fromRoutingNum);
        setField(transaction, "toAccountNum", toAccountNum);
        setField(transaction, "toRoutingNum", toRoutingNum);
        setField(transaction, "amount", amount);
        setField(transaction, "timestamp", new Date(0));
        return transaction;
    }
}
