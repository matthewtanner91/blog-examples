package example;
import org.junit.Before;
import org.junit.Test;
import org.junit.Ignore;
import org.junit.experimental.categories.Category;
import static org.junit.Assert.assertEquals;
import static org.junit.Assume.assumeTrue;
public class LegacyTest {
  public interface Smoke {}
  private int quantity;
  @Before public void setUp() { quantity = 4; }
  @Test @Category(Smoke.class)
  public void doublesQuantity() {
    assertEquals("doubled quantity", 8, quantity * 2);
  }
  @Test(expected = IllegalArgumentException.class)
  public void rejectsNegativeQuantity() { requirePositive(-1); }
  @Ignore("intentional fixture skip") @Test
  public void disabledCase() { throw new AssertionError("must not run"); }
  @Test public void absentEnvironment() { assumeTrue("no integration target", false); }
  private static void requirePositive(int value) {
    if (value < 0) throw new IllegalArgumentException("negative quantity");
  }
}
