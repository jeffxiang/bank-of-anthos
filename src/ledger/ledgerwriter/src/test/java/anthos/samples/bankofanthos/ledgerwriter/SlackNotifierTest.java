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
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.mockito.MockitoAnnotations.initMocks;

import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.springframework.http.HttpEntity;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

class SlackNotifierTest {

    @Mock
    private RestTemplate restTemplate;

    private static final String WEBHOOK_URL =
        "https://hooks.slack.com/services/test";
    private static final String CHANNEL = "#alerts";
    private static final String MESSAGE = "/transactions failed: boom";

    @BeforeEach
    void setUp() {
        initMocks(this);
    }

    @Test
    @DisplayName("Given a configured webhook, post the message to Slack")
    void notifyErrorPostsToWebhook() {
        // Given
        SlackNotifier notifier =
                new SlackNotifier(restTemplate, WEBHOOK_URL, CHANNEL);

        // When
        notifier.notifyError(MESSAGE);

        // Then
        ArgumentCaptor<HttpEntity> captor =
                ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).postForEntity(eq(WEBHOOK_URL), captor.capture(),
                eq(String.class));
        Map<String, String> payload =
                (Map<String, String>) captor.getValue().getBody();
        assertEquals("[ledgerwriter] " + MESSAGE, payload.get("text"));
        assertEquals(CHANNEL, payload.get("channel"));
    }

    @Test
    @DisplayName("Given no webhook is configured, do not call Slack")
    void notifyErrorNoOpsWhenWebhookUnset() {
        // Given
        SlackNotifier notifier = new SlackNotifier(restTemplate, "", "");

        // When
        notifier.notifyError(MESSAGE);

        // Then
        verifyNoInteractions(restTemplate);
    }

    @Test
    @DisplayName("Given a null webhook, do not call Slack")
    void notifyErrorNoOpsWhenWebhookNull() {
        // Given
        SlackNotifier notifier = new SlackNotifier(restTemplate, null, null);

        // When
        notifier.notifyError(MESSAGE);

        // Then
        verifyNoInteractions(restTemplate);
    }

    @Test
    @DisplayName("Given no channel override, post without a channel field")
    void notifyErrorPostsWithoutChannelWhenChannelNull() {
        // Given
        SlackNotifier notifier =
                new SlackNotifier(restTemplate, WEBHOOK_URL, null);

        // When
        notifier.notifyError(MESSAGE);

        // Then
        ArgumentCaptor<HttpEntity> captor =
                ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).postForEntity(eq(WEBHOOK_URL), captor.capture(),
                eq(String.class));
        Map<String, String> payload =
                (Map<String, String>) captor.getValue().getBody();
        assertNull(payload.get("channel"));
    }

    @Test
    @DisplayName("Given a timeout, construct a dedicated Slack client")
    void constructorWhenTimeoutConfiguredCreatesNotifier() {
        // When
        SlackNotifier notifier = new SlackNotifier("", "", 1);

        // Then
        assertNotNull(notifier);
    }

    @Test
    @DisplayName("Given Slack is unreachable, swallow the exception")
    void notifyErrorSwallowsSlackFailures() {
        // Given
        SlackNotifier notifier =
                new SlackNotifier(restTemplate, WEBHOOK_URL, "");
        when(restTemplate.postForEntity(eq(WEBHOOK_URL), any(HttpEntity.class),
                eq(String.class))).thenThrow(
                        new RestClientException("slack down"));

        // When
        notifier.notifyError(MESSAGE);

        // Then
        verify(restTemplate).postForEntity(eq(WEBHOOK_URL),
                any(HttpEntity.class), eq(String.class));
    }
}
