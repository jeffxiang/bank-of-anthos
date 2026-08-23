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

import java.util.HashMap;
import java.util.Map;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

/**
 * Posts error notifications to a Slack incoming webhook.
 *
 * Notifications are disabled when SLACK_WEBHOOK_URL is unset, and any failure
 * to reach Slack is logged rather than propagated to the caller.
 */
@Component
public class SlackNotifier {

    private static final Logger LOGGER =
        LogManager.getLogger(SlackNotifier.class);

    private final RestTemplate restTemplate;
    private final String webhookUrl;
    private final String channel;

    @Autowired
    public SlackNotifier(
            RestTemplate restTemplate,
            @Value("${SLACK_WEBHOOK_URL:}") String webhookUrl,
            @Value("${SLACK_CHANNEL:}") String channel) {
        this.restTemplate = restTemplate;
        this.webhookUrl = webhookUrl;
        this.channel = channel;
    }

    /**
     * Sends a message to the configured Slack channel.
     *
     * @param message  the text to post
     */
    public void notifyError(String message) {
        if (webhookUrl == null || webhookUrl.isEmpty()) {
            return;
        }
        Map<String, String> payload = new HashMap<>();
        payload.put("text", "[ledgerwriter] " + message);
        if (channel != null && !channel.isEmpty()) {
            payload.put("channel", channel);
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        try {
            restTemplate.postForEntity(webhookUrl,
                    new HttpEntity<Map<String, String>>(payload, headers),
                    String.class);
        } catch (RestClientException e) {
            LOGGER.warn("Failed to send Slack notification: "
                + e.getMessage());
        }
    }
}
