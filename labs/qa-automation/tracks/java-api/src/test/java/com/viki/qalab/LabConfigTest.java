package com.viki.qalab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;

class LabConfigTest {

    @Test
    void stripTrailingSlash_removesOneSlash() {
        assertEquals("http://x", LabConfig.stripTrailingSlash("http://x/"));
    }

    @Test
    void stripTrailingSlash_handlesNoSlash() {
        assertEquals("http://x", LabConfig.stripTrailingSlash("http://x"));
    }

    @Test
    void stripTrailingSlash_nullReturnsDefault() {
        assertFalse(LabConfig.stripTrailingSlash(null).isEmpty());
    }
}
