package example;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Tag;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
class LegacyTest {
  private int quantity;
  @BeforeEach void setUp() { quantity = 4; }
  @Test @Tag("example.LegacyTest$Smoke")
  void doublesQuantity() {
    assertEquals(8, quantity * 2, "doubled quantity");
  }
  @Test void rejectsNegativeQuantity() {
    assertThrows(IllegalArgumentException.class,
        () -> requirePositive(-1));
  }
  @Disabled("intentional fixture skip") @Test
  void disabledCase() { throw new AssertionError("must not run"); }
  @Test void absentEnvironment() { assumeTrue(false, "no integration target"); }
  private static void requirePositive(int value) {
    if (value < 0) throw new IllegalArgumentException("negative quantity");
  }
}
