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
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mockStatic;

import com.google.cloud.MetadataConfig;
import io.micrometer.stackdriver.StackdriverConfig;
import io.micrometer.stackdriver.StackdriverMeterRegistry;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.file.Paths;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import org.springframework.boot.SpringApplication;

class LedgerWriterApplicationTest {

    private static final String[] REQUIRED_ENVIRONMENT_VARIABLES = {
        "VERSION",
        "PORT",
        "LOCAL_ROUTING_NUM",
        "BALANCES_API_ADDR",
        "PUB_KEY_PATH",
        "SPRING_DATASOURCE_URL",
        "SPRING_DATASOURCE_USERNAME",
        "SPRING_DATASOURCE_PASSWORD"
    };

    @Test
    @DisplayName("Given application configuration, create its HTTP client")
    void restTemplateWhenConfiguredReturnsClient() {
        // Then
        assertNotNull(new LedgerWriterApplication().restTemplate());
    }

    @Test
    @DisplayName("Given shutdown, complete the lifecycle callback")
    void destroyWhenCalledCompletes() {
        // When
        new LedgerWriterApplication().destroy();
    }

    @Test
    @DisplayName("Given missing environment configuration, exit before startup")
    void mainWhenEnvironmentVariableMissingExits() throws Exception {
        // Given
        ProcessBuilder processBuilder = applicationProcess("missing-env");
        for (String variable : REQUIRED_ENVIRONMENT_VARIABLES) {
            processBuilder.environment().remove(variable);
        }

        // When
        int exitCode = run(processBuilder);

        // Then
        assertEquals(1, exitCode);
    }

    @Test
    @DisplayName("Given required environment configuration, start the application")
    void mainWhenEnvironmentConfiguredStartsApplication() throws Exception {
        // Given
        ProcessBuilder processBuilder = applicationProcess("configured-env");
        for (String variable : REQUIRED_ENVIRONMENT_VARIABLES) {
            processBuilder.environment().put(variable, "synthetic-value");
        }

        // When
        int exitCode = run(processBuilder);

        // Then
        assertEquals(0, exitCode);
    }

    @Test
    @DisplayName("Given metrics are disabled, build the Stackdriver registry")
    void stackdriverWhenMetricsDisabledBuildsRegistry() throws Exception {
        // Given
        ProcessBuilder processBuilder = stackdriverProcess();
        processBuilder.environment().put("ENABLE_METRICS", "false");

        // Then
        assertEquals(0, run(processBuilder));
    }

    @Test
    @DisplayName("Given metrics are enabled, build the Stackdriver registry")
    void stackdriverWhenMetricsEnabledBuildsRegistry() throws Exception {
        // Given
        ProcessBuilder processBuilder = stackdriverProcess();
        processBuilder.environment().put("ENABLE_METRICS", "true");

        // Then
        assertEquals(0, run(processBuilder));
    }

    @Test
    @DisplayName("Given no metrics override, enable the Stackdriver registry")
    void stackdriverWhenMetricsOverrideUnsetBuildsRegistry() throws Exception {
        // Given
        ProcessBuilder processBuilder = stackdriverProcess();
        processBuilder.environment().remove("ENABLE_METRICS");

        // Then
        assertEquals(0, run(processBuilder));
    }

    private ProcessBuilder stackdriverProcess() {
        ProcessBuilder processBuilder = applicationProcess("stackdriver");
        processBuilder.environment().put("HOSTNAME",
                "ledgerwriter-synthetic-123");
        processBuilder.environment().put("NAMESPACE",
                "synthetic-namespace");
        return processBuilder;
    }

    private ProcessBuilder applicationProcess(String mode) {
        String java = Paths.get(System.getProperty("java.home"), "bin",
                "java").toString();
        ProcessBuilder processBuilder = new ProcessBuilder(
                java,
                jacocoAgentArgument(),
                "-cp",
                System.getProperty("java.class.path"),
                ApplicationProcess.class.getName(),
                mode);
        processBuilder.redirectOutput(ProcessBuilder.Redirect.DISCARD);
        processBuilder.redirectError(ProcessBuilder.Redirect.DISCARD);
        return processBuilder;
    }

    private String jacocoAgentArgument() {
        return ManagementFactory.getRuntimeMXBean().getInputArguments()
                .stream()
                .filter(argument -> argument.startsWith("-javaagent:")
                        && argument.contains("org.jacoco.agent"))
                .findFirst()
                .orElseThrow();
    }

    private int run(ProcessBuilder processBuilder) throws Exception {
        Process process = processBuilder.start();
        assertTrue(process.waitFor(30, TimeUnit.SECONDS));
        return process.exitValue();
    }

    static final class ApplicationProcess {

        private static final String PROJECT_ID = "synthetic-project";

        private ApplicationProcess() {
        }

        public static void main(String[] args) throws Exception {
            if ("missing-env".equals(args[0])) {
                LedgerWriterApplication.main(new String[0]);
            } else if ("configured-env".equals(args[0])) {
                runConfiguredApplication();
            } else {
                runStackdriver();
            }
        }

        private static void runConfiguredApplication() {
            try (MockedStatic<SpringApplication> application =
                    mockStatic(SpringApplication.class)) {
                LedgerWriterApplication.main(new String[0]);
                application.verify(() -> SpringApplication.run(
                        LedgerWriterApplication.class, new String[0]));
            }
        }

        private static void runStackdriver() throws Exception {
            try (MockedStatic<MetadataConfig> metadata =
                    mockStatic(MetadataConfig.class)) {
                metadata.when(MetadataConfig::getProjectId).thenReturn(
                        PROJECT_ID);
                metadata.when(MetadataConfig::getZone).thenReturn(
                        "synthetic-zone");
                metadata.when(MetadataConfig::getClusterName).thenReturn(
                        "synthetic-cluster");
                StackdriverMeterRegistry registry =
                        LedgerWriterApplication.stackdriver();
                StackdriverConfig config = getConfig(registry);

                try {
                    assertEquals(PROJECT_ID, config.projectId());
                    metadata.when(MetadataConfig::getProjectId).thenReturn(
                            null);
                    assertEquals("", config.projectId());
                    assertEquals("k8s_container", config.resourceType());
                    assertEquals(null, config.get("unused"));
                    Map<String, String> labels = config.resourceLabels();
                    assertEquals("ledgerwriter",
                            labels.get("container_name"));
                    assertEquals("synthetic-namespace",
                            labels.get("namespace_name"));
                } finally {
                    registry.close();
                }
            }
        }

        private static StackdriverConfig getConfig(
                StackdriverMeterRegistry registry) throws Exception {
            Field field =
                    StackdriverMeterRegistry.class.getDeclaredField("config");
            field.setAccessible(true);
            return (StackdriverConfig) field.get(registry);
        }
    }
}
